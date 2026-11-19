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
def normalize(zh):
    zh = ''.join(NORM.get(c, c) for c in zh).replace('...', '…')
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

def compute(orig, tx, key):
    tr, speakers, ui = load_tx(tx)
    for k, v in DEFAULT_UI.items(): ui.setdefault(k, v)
    sarc = Archive(os.path.join(orig, 'scene.int'), key)
    carc = Archive(os.path.join(orig, 'config.int'), key)
    farc = Archive(os.path.join(orig, 'fes.int'), key)
    reserved = set()
    for e in carc.entries:
        if e[0].lower().endswith(('.csv', '.xml', '.txt')): reserved |= set(carc.read(e).decode('cp932', 'replace'))
    ui_text = ''.join(ui['scene_title'].values()) + ui['FastSceneJump'] + ''.join(v for d in ui['fes'].values() for v in d.values())
    used = set(''.join(tr.values())) | set(''.join(speakers.values())) | set(ui_text) | set('【】')
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
    a = ap.parse_args()
    orig = a.orig or a.game
    exe = os.path.join(a.game, 'GrisaiaAno3.exe')
    key = key_from_pass(pass_from_exe(exe))
    changes, enc, report, arcs = compute(orig, a.tx, key)
    os.makedirs(a.out, exist_ok=True)
    for arcname, arc in zip(('scene.int', 'config.int', 'fes.int'), arcs):
        write_archive(os.path.join(a.out, arcname), apply_python(arc, changes[arcname], key), key, arc.seed)
    open(os.path.join(a.out, 'zhtw_map.bin'), 'wb').write(enc.map_bin())
    report.update(tunnel=len(enc.map), pool_left=len(enc.pool))
    json.dump(report, open(os.path.join(a.out, '..', os.path.basename(a.out.rstrip('/\\')) + '-report.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    if a.payload:
        def sha(p): return hashlib.sha256(open(p, 'rb').read()).hexdigest()
        arcs_j = {}
        for arcname in ('scene.int', 'config.int', 'fes.int'):
            ents = {}
            for n, spec in changes[arcname].items():
                if spec['type'] == 'cst': ents[n] = {'type': 'cst', 'lines': {k: [h, b64(v)] for k, (h, v) in spec['lines'].items()}}
                elif spec['type'] == 'append': ents[n] = {'type': 'append', 'data': b64(spec['data'])}
                else: ents[n] = {'type': 'fes', 'replace': [[b64(x), b64(y)] for x, y in spec['replace']]}
            arcs_j[arcname] = {'orig_sha256': sha(os.path.join(orig, arcname)), 'entries': ents}
        files = {'zhtw_map.bin': b64(enc.map_bin())}
        if a.ini: files['zhtw.ini'] = b64(open(a.ini, 'rb').read())
        pj = {'version': a.version, 'key': key, 'exe_sha256': [sha(exe)], 'archives': arcs_j, 'files': files}
        json.dump(pj, open(a.payload, 'w', encoding='utf-8'), ensure_ascii=True)
    print(json.dumps({k: v for k, v in report.items() if k != 'missing'}, ensure_ascii=False), 'missing', len(report['missing']))

if __name__ == '__main__':
    main()
