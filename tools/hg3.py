"""CatSystem2 HG-3 影像（img0000 無損格式）解碼／編碼。

結構：'HG-3' + uint32 0x0C + uint32 版本 ；之後為多個 frame：
  frame：uint32 到下一 frame 的位移(0=最後)、uint32 id，接著多個 tag：
  tag  ：name[8] + uint32 到下一 tag 的位移(0=最後) + uint32 內容長度 + 內容
  stdinfo：width, height, bpp, offset_x, offset_y, canvas_w, canvas_h, ...
  img0000：uint32 top, uint32 height, uint32 data_packed, data_size, ctl_packed, ctl_size, data(zlib), ctl(zlib)
解碼：控制位元流（Elias-gamma）把「資料／零」區段展開 → 4 平面重排＋符號轉換 → 上→下差分 → 影像列由下往上。
編碼採最簡單合法控制流：單一「資料」區段（不壓零），可被引擎正常解碼。
python hg3.py dec IN.hg3 OUT_DIR   → 每個 frame 存 PNG（RGBA）
python hg3.py enc IN.hg3 PNG_DIR OUT.hg3  → 以 PNG 取代各 frame 像素（尺寸須相同），其餘 tag 原樣保留
"""
import struct, sys, os, zlib
import numpy as np

def _table():
    t = np.zeros((4, 256), dtype=np.uint32)
    for i in range(256):
        v = (((((i & 0xC0) << 6) | (i & 0x30)) << 6 | (i & 0x0C)) << 6) | (i & 0x03)
        t[0, i] = v << 6; t[1, i] = v << 4; t[2, i] = v << 2; t[3, i] = v
    return t
TAB = _table()

class BitReader:
    def __init__(self, data): self.d = data; self.p = 0
    def bit(self):
        b = (self.d[self.p >> 3] >> (self.p & 7)) & 1; self.p += 1; return b
    def gamma(self):
        n = 0
        while self.bit() == 0:
            n += 1
            if n >= 32: raise ValueError('gamma overflow')
        v = 1
        for _ in range(n): v = (v << 1) | self.bit()
        return v

class BitWriter:
    def __init__(self): self.out = bytearray(); self.n = 0
    def bit(self, b):
        if self.n % 8 == 0: self.out.append(0)
        if b: self.out[-1] |= 1 << (self.n % 8)
        self.n += 1
    def gamma(self, v):
        bits = v.bit_length()
        for _ in range(bits - 1): self.bit(0)
        self.bit(1)
        for i in range(bits - 2, -1, -1): self.bit((v >> i) & 1)

def conv(b):  # 符號轉換的逆運算查表
    b = b.astype(np.uint8); carry = b & 1; v = b >> 1
    return np.where(carry == 1, v ^ 0xFF, v).astype(np.uint8)

INV = np.zeros(256, dtype=np.uint8)
for x in range(256):
    INV[int(conv(np.array([x]))[0])] = x

def decode_img(width, height, bpp, data, ctl):
    br = BitReader(ctl); copy = br.bit(); size = br.gamma()
    out = np.zeros(size, dtype=np.uint8); src = dst = 0
    while dst < size:
        c = br.gamma()
        if copy: out[dst:dst + c] = np.frombuffer(data, dtype=np.uint8, count=c, offset=src); src += c
        dst += c; copy ^= 1
    q = size // 4
    v = TAB[0][out[:q]] | TAB[1][out[q:2 * q]] | TAB[2][out[2 * q:3 * q]] | TAB[3][out[3 * q:]]
    b = v.view(np.uint8).reshape(-1)  # little-endian 4 bytes per value
    b = conv(b)
    ps = bpp // 8; stride = width * ps
    img = b[:height * stride].reshape(height, stride).astype(np.uint8)
    # 第一列：水平差分；其餘列：與上一列差分（uint8 溢位）
    first = img[0].reshape(width, ps)
    img[0] = np.cumsum(first, axis=0, dtype=np.uint8).reshape(-1)
    img = np.cumsum(img, axis=0, dtype=np.uint8)
    img = img.reshape(height, width, ps)[::-1]   # 資料由下往上
    return img  # BGR(A)

def encode_img(img, bpp):
    """img：height x width x ps（BGR(A)，上→下）。回傳 (data_packed, data_size, ctl_packed, ctl_size, bytes)。"""
    h, w, ps = img.shape
    a = img[::-1].reshape(h, w * ps).astype(np.uint8)
    d = a.copy(); d[1:] = (a[1:].astype(np.int16) - a[:-1]).astype(np.uint8)
    r0 = a[0].reshape(w, ps).astype(np.int16); r0d = r0.copy(); r0d[1:] = r0[1:] - r0[:-1]
    d[0] = r0d.astype(np.uint8).reshape(-1)
    flat = INV[d.reshape(-1)]
    if len(flat) % 4: flat = np.concatenate([flat, np.zeros(4 - len(flat) % 4, dtype=np.uint8)])
    v = flat.view(np.uint32)
    planes = []
    for k, sh in enumerate((6, 4, 2, 0)):
        x = (v >> sh)
        p = ((x & 0x3) | ((x >> 6) & 0xC) | ((x >> 12) & 0x30) | ((x >> 18) & 0xC0)).astype(np.uint8)
        planes.append(p)
    raw = np.concatenate(planes).tobytes()
    bw = BitWriter(); bw.bit(1); bw.gamma(len(raw)); bw.gamma(len(raw))
    ctl = bytes(bw.out)
    dz, cz = zlib.compress(raw, 9), zlib.compress(ctl, 9)
    return struct.pack('<IIII', len(dz), len(raw), len(cz), len(ctl)) + dz + cz

def parse(buf):
    assert buf[:4] == b'HG-3'
    hsize = struct.unpack_from('<I', buf, 4)[0]
    frames = []; pos = hsize
    while True:
        nxt, fid = struct.unpack_from('<II', buf, pos)
        tags = []; tp = pos + 8
        while True:
            raw = buf[tp:tp + 8]; tn, tl = struct.unpack_from('<II', buf, tp + 8)
            tags.append([raw.split(b'\0')[0].decode('ascii', 'replace'), buf[tp + 16:tp + 16 + tl], raw])
            if tn == 0: break
            tp += tn
        frames.append({'id': fid, 'tags': tags})
        if nxt == 0: break
        pos += nxt
    return buf[:hsize], frames

def build(head, frames):
    out = bytearray(head)
    for fi, fr in enumerate(frames):
        fb = bytearray()
        for ti, (name, body, raw) in enumerate(fr['tags']):
            last = ti == len(fr['tags']) - 1
            fb += raw + struct.pack('<II', 0 if last else 16 + len(body), len(body)) + body
        lastf = fi == len(frames) - 1
        out += struct.pack('<II', 0 if lastf else 8 + len(fb), fr['id']) + fb
    return bytes(out)

def stdinfo(body): return struct.unpack_from('<IIIiiII', body, 0)

def frame_image(fr):
    info = next(t[1] for t in fr['tags'] if t[0] == 'stdinfo'); w, h, bpp = stdinfo(info)[:3]
    img = next((t[1] for t in fr['tags'] if t[0].startswith('img00')), None)
    if img is None: return None
    top, hh, dp, ds, cp, cs = struct.unpack_from('<IIIIII', img, 0)
    data = zlib.decompress(img[24:24 + dp]); ctl = zlib.decompress(img[24 + dp:24 + dp + cp])
    return decode_img(w, h, bpp, data, ctl), (w, h, bpp, stdinfo(info))

def to_png(arr, path):
    from PIL import Image
    if arr.shape[2] == 4: Image.fromarray(arr[:, :, [2, 1, 0, 3]], 'RGBA').save(path)
    else: Image.fromarray(arr[:, :, [2, 1, 0]], 'RGB').save(path)

def from_png(path, ps):
    from PIL import Image
    im = Image.open(path).convert('RGBA' if ps == 4 else 'RGB'); a = np.array(im)
    return a[:, :, [2, 1, 0, 3]] if ps == 4 else a[:, :, [2, 1, 0]]

if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'dec':
        buf = open(sys.argv[2], 'rb').read(); _, frames = parse(buf); os.makedirs(sys.argv[3], exist_ok=True)
        base = os.path.splitext(os.path.basename(sys.argv[2]))[0]
        for i, fr in enumerate(frames):
            r = frame_image(fr)
            if r is None: continue
            arr, (w, h, bpp, info) = r
            to_png(arr, os.path.join(sys.argv[3], f'{base}#{i:03d}.png'))
            print(i, fr['id'], w, h, bpp, 'off', info[3], info[4], 'canvas', info[5], info[6])
    elif cmd == 'enc':
        buf = open(sys.argv[2], 'rb').read(); head, frames = parse(buf)
        base = os.path.splitext(os.path.basename(sys.argv[2]))[0]
        for i, fr in enumerate(frames):
            p = os.path.join(sys.argv[3], f'{base}#{i:03d}.png')
            if not os.path.exists(p): continue
            info = next(t[1] for t in fr['tags'] if t[0] == 'stdinfo'); w, h, bpp = stdinfo(info)[:3]
            arr = from_png(p, bpp // 8); assert arr.shape[:2] == (h, w), (p, arr.shape, w, h)
            for t in fr['tags']:
                if t[0].startswith('img00'):
                    top, hh = struct.unpack_from('<II', t[1], 0)
                    t[1] = struct.pack('<II', top, hh) + encode_img(arr, bpp)
        open(sys.argv[4], 'wb').write(build(head, frames)); print('ok')
