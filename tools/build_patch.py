"""繁中補丁組裝（lab 與發行共用）。

python build_patch.py --game GAME_DIR --tx TX_DIR --out OUT_DIR [--orig ORIG_DIR] [--payload PAYLOAD.json --version X.Y.Z]
  --game : 日文版遊戲資料夾（讀 GrisaiaAno3.exe 取金鑰）
  --orig : 原版 .int 來源（預設 = --game；已安裝補丁時請指向 _zhTW_backup）
  --tx   : 譯文資料夾（out-*.json / fix-*.json：[{id, zh}]；glossary.zh-TW.json 的 speakers；ui.zh-TW.json）
輸出：OUT_DIR\\scene.int、config.int、fes.int、zhtw_map.bin、build-report.json（lab 直接用）
      --payload：另輸出安裝程式用 payload.json（只含譯文位元組與原文列雜湊，不含原版檔案內容）

編碼策略（引擎只吃 CP932 位元組）：
  * 能以 CP932 原樣表示的字 → 直接用 CP932。
  * 其餘繁體字 → 借用譯文與遊戲其他文字都沒用到的 CP932 第二水準漢字碼（隧道碼），
    zhtw_map.bin 記錄 隧道碼 → Unicode，由 version.dll 在解碼／取字形時換回。
"""
import argparse, base64, hashlib, json, os, re, struct, sys, glob, zlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cs2int import Archive, write_archive, pass_from_exe, key_from_pass
from cst import Scene
import hg3 as HG

def cp932_roundtrip(c):
    try: b = c.encode('cp932')
    except UnicodeEncodeError: return None
    return b if b.decode('cp932') == c else None

class Encoder:
    def __init__(self, used_chars, reserved_chars):
        self.map = {}; busy = set(used_chars) | set(reserved_chars); pool = []
        # 第二水準漢字 0x989F..0xEAA4 由後往前；第二位元組只用 0x80 以上，避開 \ [ ] @ 等 ASCII
        for lead in range(0xEA, 0x97, -1):
            for trail in range(0xFC, 0x7F, -1):
                try: ch = bytes([lead, trail]).decode('cp932')
                except UnicodeDecodeError: continue
                if len(ch) != 1 or ch in busy or not ('一' <= ch <= '鿿'): continue
                pool.append((lead << 8) | trail)
        self.pool = pool
    def code_for(self, c):
        if c not in self.map:
            if not self.pool: raise RuntimeError('隧道碼用盡')
            self.map[c] = self.pool.pop(0)
        return self.map[c]
    def encode(self, s):
        out = bytearray()
        for c in s:
            b = cp932_roundtrip(c)
            out += b if b is not None else struct.pack('>H', self.code_for(c))
        return bytes(out)
    def map_bin(self):
        items = sorted((code, ord(c)) for c, code in self.map.items())
        return b'ZHMP' + struct.pack('<I', len(items)) + b''.join(struct.pack('<HH', a, b) for a, b in items)

NORM = {'—': '─', '―': '─', '·': '‧', '・': '‧', '[': '［', ']': '］', '\\': '＼', '@': '＠', '#': '＃', '　': '　'}
ELLIPSIS = os.environ.get('ZHTW_ELLIPSIS', '⋯')   # 台灣排版常用置中刪節號；正黑體的「…」字寬較窄，在引擎全形格中會斷開
def normalize(zh):
    zh = ''.join(NORM.get(c, c) for c in zh).replace('...', '…').replace('…', ELLIPSIS)
    return zh.strip()

def sha16(b): return hashlib.sha256(b).hexdigest()[:16]

def load_tx(tx):
    tr = {}
    for pat in ('out-*.json', 'fix-*.json'):
        for f in sorted(glob.glob(os.path.join(tx, pat))):
            for o in json.load(open(f, encoding='utf-8')): tr[o['id']] = normalize(o['zh'])
    gl = json.load(open(os.path.join(tx, 'glossary.zh-TW.json'), encoding='utf-8'))
    ui_path = os.path.join(tx, 'ui.zh-TW.json')
    ui = json.load(open(ui_path, encoding='utf-8')) if os.path.exists(ui_path) else {}
    return tr, gl['speakers'], ui

DEFAULT_UI = {
    'scene_title': {'グリザイアの旋律': '灰色的旋律'},
    'FastSceneJump': '找不到跳轉目的地',
    'fes': {'_saveload.fes': {'グリザイアの旋律１': '灰色的旋律１', 'グリザイアの旋律２': '灰色的旋律２',
                              'グリザイアの旋律３': '灰色的旋律３', 'グリザイアの旋律４': '灰色的旋律４',
                              'ここにタイトルが入力される': '此處會填入標題', 'メッセージを入力してください': '請輸入訊息'}},
}

def load_lang(lang_dir):
    if not lang_dir: return {}
    d = {}
    for f in sorted(glob.glob(os.path.join(lang_dir, 'lang-out-*.json'))):
        for o in json.load(open(f, encoding='utf-8')): d[o['id']] = o['zh']
    return d

def build_language_txt(lang, enc):
    """language.txt：引擎不轉碼、直接把位元組交給 A 版 API，故寫成 CP932＋隧道碼（與劇本相同），由 hook 解回 Unicode。
    不寫日文原文註解，只有編號與譯文。"""
    out = [b'// zh-TW string table (CP932 + tunnel codes; see zhtw_map.bin)', b'// $nr$ / $empty$', b'']
    for i in sorted(lang):
        zh = lang[i].replace('\r', '')
        out += [('$%s$' % i).encode('ascii'), enc.encode(zh) if zh else b'$empty$', b'']
    return b'\r\n'.join(out) + b'\r\n'

def compute(orig, tx, key, lang=None):
    tr, speakers, ui = load_tx(tx)
    lang = lang or {}
    for k, v in DEFAULT_UI.items(): ui.setdefault(k, v)
    sarc = Archive(os.path.join(orig, 'scene.int'), key)
    carc = Archive(os.path.join(orig, 'config.int'), key)
    farc = Archive(os.path.join(orig, 'fes.int'), key)
    reserved = set()
    for e in carc.entries:
        if e[0].lower().endswith(('.csv', '.xml', '.txt')): reserved |= set(carc.read(e).decode('cp932', 'replace'))
    ui_text = ''.join(ui['scene_title'].values()) + ui['FastSceneJump'] + ''.join(v for d in ui['fes'].values() for v in d.values())
    used = set(''.join(tr.values())) | set(''.join(speakers.values())) | set(ui_text) | set('【】') | set(''.join(lang.values()))
    enc = Encoder(used, reserved)
    changes = {'scene.int': {}, 'config.int': {}, 'fes.int': {}}
    report = {'missing': [], 'scenes': {}}

    for e in sarc.entries:
        name = e[0]
        if not name.lower().endswith('.cst'): continue
        sc = Scene.load(sarc.read(e))
        key_ = name[len('gri_ano03_'):-4] if name.startswith('gri_') else None
        lines = {}; n_msg = n_tr = 0
        for i, (t, s) in enumerate(sc.lines):
            u = s.decode('cp932'); new = None
            if t == 0x21 and u in speakers: new = enc.encode(speakers[u])
            elif t == 0x20 and u.strip():
                if name == 'FastSceneJump.cst': new = enc.encode(ui['FastSceneJump'])
                elif key_:
                    n_msg += 1; tid = f'{key_}:{i:04d}'
                    if tid in tr:
                        new = enc.encode(tr[tid]) + (b'\\@' if u.endswith('\\@') else b''); n_tr += 1
                    else: report['missing'].append(tid)
            elif t == 0x30 and u.startswith('str '):
                for ja, zh in ui['scene_title'].items():
                    if ja in u: new = enc.encode(u.replace(ja, zh))
            if new is not None and new != s: lines[str(i)] = [sha16(s), new]
        if lines: changes['scene.int'][name] = {'type': 'cst', 'lines': lines}
        if key_: report['scenes'][name] = {'messages': n_msg, 'translated': n_tr}

    nt = carc.read('nametable.csv'); add = b''
    for r in nt.split(b'\r\n'):
        m = re.match(r'^(\d+)\t"(【?)([^"】]*)(】?)"(.*)$', r.decode('cp932'))
        if m and m.group(3) in speakers:
            add += b'\r\n' + enc.encode(f'{m.group(1)}\t"{m.group(2)}{speakers[m.group(3)]}{m.group(4)}"{m.group(5)}')
    changes['config.int']['nametable.csv'] = {'type': 'append', 'data': add}

    for fname, rep in ui['fes'].items():
        d = farc.read(fname); cs, ds = struct.unpack_from('<II', d, 4)
        text = zlib.decompress(d[16:16 + cs]); pairs = []
        for ja, zh in rep.items():
            a = ja.encode('cp932')
            if a in text: pairs.append([a, enc.encode(zh)])
        changes['fes.int'][fname] = {'type': 'fes', 'replace': pairs}
    return changes, enc, report, (sarc, carc, farc)

def compute_images(orig, key, ui_out):
    """ui_out：重繪後的 <file>#NNN.png（＋.json offset）。回傳 image.int 的修補規格：每個 frame 的新 stdinfo 與 img 標籤內容。"""
    if not ui_out or not os.path.isdir(ui_out): return {}, None
    by_file = {}
    for f in glob.glob(os.path.join(ui_out, '*#*.png')):
        b = os.path.basename(f)[:-4]; name, idx = b.rsplit('#', 1); by_file.setdefault(name, []).append(int(idx))
    if not by_file: return {}, None
    iarc = Archive(os.path.join(orig, 'image.int'), key)
    spec = {}
    for name, frames in sorted(by_file.items()):
        data = iarc.read(name + '.hg3'); head, frs = HG.parse(data); fs = {}
        for i in sorted(frames):
            fr = frs[i]; ti = next(k for k, t in enumerate(fr['tags']) if t[0] == 'stdinfo'); info = fr['tags'][ti][1]
            w, h, bpp, ox, oy = HG.stdinfo(info)[:5]
            png = os.path.join(ui_out, f'{name}#{i:03d}.png'); arr = HG.from_png(png, bpp // 8); nh, nw = arr.shape[:2]
            side = png[:-4] + '.json'
            if os.path.exists(side): j = json.load(open(side)); ox, oy = j.get('x', ox), j.get('y', oy)
            new_info = struct.pack('<IIIii', nw, nh, bpp, ox, oy) + info[20:]
            it = next(t for t in fr['tags'] if t[0].startswith('img00'))
            top = struct.unpack_from('<I', it[1], 0)[0]
            new_img = struct.pack('<II', 0 if nh != h else top, nh) + HG.encode_img(arr, bpp)
            fs[str(i)] = {'img_sha': sha16(it[1]), 'stdinfo': new_info, 'img': new_img}
        spec[name + '.hg3'] = {'type': 'hg3', 'frames': fs}
    return spec, iarc

def patch_hg3(data, spec):
    head, frs = HG.parse(data)
    for k, v in spec['frames'].items():
        fr = frs[int(k)]
        for t in fr['tags']:
            if t[0] == 'stdinfo': t[1] = v['stdinfo']
            elif t[0].startswith('img00'):
                assert sha16(t[1]) == v['img_sha']; t[1] = v['img']
    return HG.build(head, frs)

def apply_python(arc, spec_map, key):
    files = []
    for e in arc.entries:
        data = arc.read(e); spec = spec_map.get(e[0])
        if spec and spec['type'] == 'cst':
            sc = Scene.load(data)
            for k, (h, new) in spec['lines'].items():
                assert sha16(sc.lines[int(k)][1]) == h; sc.lines[int(k)][1] = new
            data = sc.dump()
        elif spec and spec['type'] == 'append': data = data + spec['data']
        elif spec and spec['type'] == 'hg3': data = patch_hg3(data, spec)
        elif spec and spec['type'] == 'fes':
            cs, ds = struct.unpack_from('<II', data, 4); text = zlib.decompress(data[16:16 + cs])
            for a, b in spec['replace']: text = text.replace(a, b, 1)
            comp = zlib.compress(text, 9)
            data = data[:4] + struct.pack('<II', len(comp), len(text)) + data[12:16] + comp
        files.append((e[0], data))
    return files

def b64(b): return base64.b64encode(b).decode('ascii')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--game', required=True); ap.add_argument('--tx', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--orig'); ap.add_argument('--payload'); ap.add_argument('--version', default='0.0.0')
    ap.add_argument('--ini', help='zhtw.ini 內容來源檔（payload 用）')
    ap.add_argument('--lang', help='language.txt 譯文資料夾（lang-out-*.json）')
    ap.add_argument('--ui', help='UI 重繪結果資料夾（<file>#NNN.png）')
    a = ap.parse_args()
    orig = a.orig or a.game
    exe = os.path.join(a.game, 'GrisaiaAno3.exe')
    key = key_from_pass(pass_from_exe(exe))
    lang = load_lang(a.lang)
    changes, enc, report, arcs = compute(orig, a.tx, key, lang)
    img_spec, iarc = compute_images(orig, key, a.ui)
    names, arclist = ['scene.int', 'config.int', 'fes.int'], list(arcs)
    if img_spec: changes['image.int'] = img_spec; names.append('image.int'); arclist.append(iarc)
    os.makedirs(a.out, exist_ok=True)
    for arcname, arc in zip(names, arclist):
        write_archive(os.path.join(a.out, arcname), apply_python(arc, changes[arcname], key), key, arc.seed)
    lang_bytes = build_language_txt(lang, enc) if lang else None
    if lang_bytes: open(os.path.join(a.out, 'language.txt'), 'wb').write(lang_bytes)
    open(os.path.join(a.out, 'zhtw_map.bin'), 'wb').write(enc.map_bin())
    report.update(tunnel=len(enc.map), pool_left=len(enc.pool))
    json.dump(report, open(os.path.join(a.out, '..', os.path.basename(a.out.rstrip('/\\')) + '-report.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    if a.payload:
        def sha(p): return hashlib.sha256(open(p, 'rb').read()).hexdigest()
        arcs_j = {}
        for arcname in names:
            ents = {}
            for n, spec in changes[arcname].items():
                if spec['type'] == 'cst': ents[n] = {'type': 'cst', 'lines': {k: [h, b64(v)] for k, (h, v) in spec['lines'].items()}}
                elif spec['type'] == 'append': ents[n] = {'type': 'append', 'data': b64(spec['data'])}
                elif spec['type'] == 'hg3': ents[n] = {'type': 'hg3', 'frames': {k: {'img_sha': v['img_sha'], 'stdinfo': b64(v['stdinfo']), 'img': b64(v['img'])} for k, v in spec['frames'].items()}}
                else: ents[n] = {'type': 'fes', 'replace': [[b64(x), b64(y)] for x, y in spec['replace']]}
            arcs_j[arcname] = {'orig_sha256': sha(os.path.join(orig, arcname)), 'entries': ents}
        files = {'zhtw_map.bin': b64(enc.map_bin())}
        if lang_bytes: files['language.txt'] = b64(lang_bytes)
        if a.ini: files['zhtw.ini'] = b64(open(a.ini, 'rb').read())
        pj = {'version': a.version, 'key': key, 'exe_sha256': [sha(exe)], 'archives': arcs_j, 'files': files}
        json.dump(pj, open(a.payload, 'w', encoding='utf-8'), ensure_ascii=True)
    print(json.dumps({k: v for k, v in report.items() if k != 'missing'}, ensure_ascii=False), 'missing', len(report['missing']))

if __name__ == '__main__':
    main()
