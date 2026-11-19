"""CatSystem2 KIF (.int) archive tool — list / extract / pack (encrypted or plain).

Format notes (from GARbro ArcINT.cs, MIT):
  header  "KIF\\0" + int32 count
  entry   name[0x40] + uint32 offset + uint32 size   (0x48 bytes)
  encrypted archives start with entry "__key__.dat" whose size field is the MT seed;
  blowfish key = LE bytes of MT(seed).rand(); entry offset/size are blowfish-deciphered
  (offset stored minus index), names obfuscated with an MT-derived alphabet shift,
  file bodies blowfish-deciphered (whole 8-byte blocks, little-endian words).
  main_key = CRC-like hash of the passphrase stored in exe resource V_CODE2 (blowfish with KEY_CODE^0xCD).

Only standard library + pycryptodome (Blowfish).  Usage:
  python cs2int.py key   GAME.exe
  python cs2int.py list  ARCHIVE.int  --exe GAME.exe
  python cs2int.py x     ARCHIVE.int  OUTDIR --exe GAME.exe [--only NAME ...]
  python cs2int.py pack  ORIG.int SRCDIR OUT.int --exe GAME.exe   (rebuild with same order; replaced files taken from SRCDIR)
"""
import argparse, os, struct, sys
from Crypto.Cipher import Blowfish as _BF

# ---------------- helpers ----------------
def _swap32(b):
    a = bytearray(b)
    n = len(a) // 4 * 4
    a[0:n:4], a[1:n:4], a[2:n:4], a[3:n:4] = a[3:n:4], a[2:n:4], a[1:n:4], a[0:n:4]
    return bytes(a)

class BF:
    """Blowfish with little-endian 32-bit words (as used by CatSystem2)."""
    def __init__(self, key):
        self.c = _BF.new(bytes(key), _BF.MODE_ECB)
    def dec(self, data):
        n = len(data) // 8 * 8
        if n == 0: return bytes(data)
        return _swap32(self.c.decrypt(_swap32(bytes(data[:n])))) + bytes(data[n:])
    def enc(self, data):
        n = len(data) // 8 * 8
        if n == 0: return bytes(data)
        return _swap32(self.c.encrypt(_swap32(bytes(data[:n])))) + bytes(data[n:])
    def dec_pair(self, l, r):
        out = self.dec(struct.pack('<II', l, r)); return struct.unpack('<II', out)
    def enc_pair(self, l, r):
        out = self.enc(struct.pack('<II', l, r)); return struct.unpack('<II', out)

class MT:
    N, M = 624, 397
    def __init__(self, seed): self.srand(seed)
    def srand(self, seed):
        mt = [0] * self.N; seed &= 0xffffffff
        for i in range(self.N):
            upper = seed & 0xffff0000
            seed = (69069 * seed + 1) & 0xffffffff
            mt[i] = upper | ((seed & 0xffff0000) >> 16)
            seed = (69069 * seed + 1) & 0xffffffff
        self.mt, self.mti = mt, self.N
    def rand(self):
        N, M, mt = self.N, self.M, self.mt
        if self.mti >= N:
            for kk in range(N):
                y = (mt[kk] & 0x80000000) | (mt[(kk + 1) % N] & 0x7fffffff)
                mt[kk] = mt[(kk + M) % N] ^ (y >> 1) ^ (0x9908B0DF if y & 1 else 0)
            self.mti = 0
        y = mt[self.mti]; self.mti += 1
        y ^= y >> 11; y ^= (y << 7) & 0x9D2C5680; y ^= (y << 15) & 0xEFC60000; y ^= y >> 18
        return y & 0xffffffff

_CRC_TABLE = []
for _i in range(256):
    _c = _i << 24
    for _ in range(8):
        _c = ((_c << 1) ^ 0x04C11DB7) if _c & 0x80000000 else (_c << 1)
    _CRC_TABLE.append(_c & 0xffffffff)

def key_from_pass(password):
    key = 0xffffffff
    for c in password.encode('cp932'):
        key = (~_CRC_TABLE[((key >> 24) ^ c) & 0xff] ^ (key << 8)) & 0xffffffff
    return key

def pass_from_exe(exe_path):
    import pefile
    pe = pefile.PE(exe_path, fast_load=True)
    pe.parse_data_directories([pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_RESOURCE']])
    res = {}
    for t in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        tname = str(t.name) if t.name else t.id
        for e in t.directory.entries:
            ename = str(e.name) if e.name else e.id
            d = e.directory.entries[0].data.struct
            res[(tname, ename)] = pe.get_data(d.OffsetToData, d.Size)
    code = bytearray(res[('V_CODE2', 'DATA')]) if ('V_CODE2', 'DATA') in res else None
    if code is None:
        # some builds swap type/name
        code = bytearray(next(v for (t, n), v in res.items() if 'V_CODE2' in (str(t), str(n))))
    key = next((v for (t, n), v in res.items() if 'KEY_CODE' in (str(t), str(n))), None)
    key = bytes(b ^ 0xCD for b in key) if key else b'windmill'
    plain = BF(key).dec(bytes(code))
    plain = plain.split(b'\0', 1)[0]
    return plain.decode('cp932')

ALPHA = "zyxwvutsrqponmlkjihgfedcbaZYXWVUTSRQPONMLKJIHGFEDCBA"

def decipher_name(buf, key):
    k = ((key >> 24) + (key >> 16) + (key >> 8) + key) & 0xff
    out = bytearray()
    for b in buf:
        if b == 0: break
        ch = chr(b); j = ALPHA.find(ch)
        if j != -1:
            j -= k % 0x34
            if j < 0: j += 0x34
            b = ord(ALPHA[0x33 - j])
        out.append(b); k += 1
    return out.decode('cp932')

def encipher_name(name, key):
    raw = name.encode('cp932')
    k = ((key >> 24) + (key >> 16) + (key >> 8) + key) & 0xff
    out = bytearray()
    for b in raw:
        ch = chr(b); p = ALPHA.find(ch)
        if p != -1:
            j = 0x33 - p          # value after "j -= k%0x34" step
            j += k % 0x34         # undo the shift
            if j >= 0x34: j -= 0x34
            b = ord(ALPHA[j])
        out.append(b); k += 1
    return bytes(out)

# ---------------- archive ----------------
class Archive:
    def __init__(self, path, main_key=None):
        self.path = path
        self.f = open(path, 'rb')
        hdr = self.f.read(8)
        if hdr[:4] != b'KIF\0': raise ValueError('not a KIF archive')
        self.count = struct.unpack('<i', hdr[4:])[0]
        self.raw_dir = self.f.read(0x48 * self.count)
        first = self.raw_dir[:0x40].split(b'\0', 1)[0]
        self.encrypted = first == b'__key__.dat'
        self.entries = []   # (name, offset, size)
        if self.encrypted:
            if main_key is None: raise ValueError('encrypted archive needs --exe')
            self.main_key = main_key
            self.seed = struct.unpack_from('<I', self.raw_dir, 0x44)[0]
            tw = MT(self.seed)
            self.bf = BF(struct.pack('<I', tw.rand()))
            for i in range(1, self.count):
                o = 0x48 * i
                nb = self.raw_dir[o:o + 0x40]
                off, size = struct.unpack_from('<II', self.raw_dir, o + 0x40)
                off = (off + i) & 0xffffffff
                off, size = self.bf.dec_pair(off, size)
                tw.srand((main_key + i) & 0xffffffff)
                name = decipher_name(nb, tw.rand())
                self.entries.append((name, off, size))
        else:
            for i in range(self.count):
                o = 0x48 * i
                name = self.raw_dir[o:o + 0x40].split(b'\0', 1)[0].decode('cp932')
                off, size = struct.unpack_from('<II', self.raw_dir, o + 0x40)
                self.entries.append((name, off, size))
    def read(self, name_or_entry):
        e = name_or_entry if isinstance(name_or_entry, tuple) else next(x for x in self.entries if x[0] == name_or_entry)
        self.f.seek(e[1]); data = self.f.read(e[2])
        return self.bf.dec(data) if self.encrypted else data

def write_archive(out_path, files, main_key=None, seed=None):
    """files: list of (name, bytes). Encrypted when main_key given (same scheme as original)."""
    n = len(files) + (1 if main_key is not None else 0)
    hdr = bytearray(b'KIF\0' + struct.pack('<i', n))
    dir_size = 0x48 * n
    data_off = 8 + dir_size
    dirb = bytearray(dir_size)
    bodies = []
    if main_key is not None:
        tw = MT(seed)
        bf = BF(struct.pack('<I', tw.rand()))
        dirb[0:12] = b'__key__.dat\0'
        struct.pack_into('<II', dirb, 0x40, 0, seed)
        pos = data_off
        for i, (name, data) in enumerate(files, start=1):
            tw.srand((main_key + i) & 0xffffffff)
            nb = encipher_name(name, tw.rand())
            if len(nb) > 0x40: raise ValueError('name too long: ' + name)
            o = 0x48 * i
            dirb[o:o + len(nb)] = nb
            eo, es = bf.enc_pair(pos, len(data))
            struct.pack_into('<II', dirb, o + 0x40, (eo - i) & 0xffffffff, es)
            bodies.append(bf.enc(data)); pos += len(data)
    else:
        pos = data_off
        for i, (name, data) in enumerate(files):
            nb = name.encode('cp932'); o = 0x48 * i
            dirb[o:o + len(nb)] = nb
            struct.pack_into('<II', dirb, o + 0x40, pos, len(data))
            bodies.append(data); pos += len(data)
    tmp = out_path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(hdr); f.write(dirb)
        for b in bodies: f.write(b)
    os.replace(tmp, out_path)

def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd', required=True)
    k = sp.add_parser('key'); k.add_argument('exe')
    l = sp.add_parser('list'); l.add_argument('arc'); l.add_argument('--exe')
    x = sp.add_parser('x'); x.add_argument('arc'); x.add_argument('out'); x.add_argument('--exe'); x.add_argument('--only', nargs='*')
    p = sp.add_parser('pack'); p.add_argument('orig'); p.add_argument('src'); p.add_argument('out'); p.add_argument('--exe'); p.add_argument('--plain', action='store_true')
    a = ap.parse_args()
    mk = key_from_pass(pass_from_exe(a.exe)) if getattr(a, 'exe', None) else None
    if a.cmd == 'key':
        pw = pass_from_exe(a.exe); print('passphrase', pw, 'key', hex(key_from_pass(pw))); return
    arc = Archive(a.arc, mk)
    if a.cmd == 'list':
        print('encrypted' if arc.encrypted else 'plain', len(arc.entries))
        for n, o, s in arc.entries: print(f'{o:10d} {s:9d} {n}')
    elif a.cmd == 'x':
        os.makedirs(a.out, exist_ok=True); c = 0
        for e in arc.entries:
            if a.only and e[0] not in a.only: continue
            with open(os.path.join(a.out, e[0]), 'wb') as f: f.write(arc.read(e)); c += 1
        print('extracted', c)
    elif a.cmd == 'pack':
        files, repl = [], 0
        for e in arc.entries:
            sp_ = os.path.join(a.src, e[0])
            if os.path.exists(sp_):
                data = open(sp_, 'rb').read(); repl += 1
            else:
                data = arc.read(e)
            files.append((e[0], data))
        write_archive(a.out, files, None if a.plain else (mk if arc.encrypted else None), getattr(arc, 'seed', None))
        print('packed', len(files), 'replaced', repl)

if __name__ == '__main__':
    main()
