"""從日文版 scene CST 抽出待譯單位（只在 lab 使用；含原文，絕不入庫）。
python extract_ja.py SCENE_DIR OUTDIR [每批數量]
輸出 in-NNN.json：[{"id","speaker","ja","ja_len","ctx"}]，以及 all-units.json
"""
import sys, os, re, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cst import Scene

def clean_ja(u):
    tail = ''
    if u.endswith('\\@'): u, tail = u[:-2], '\\@'
    u = u.replace('\\n', '')
    u = re.sub(r'\[([^\]/]*)\]', r'\1', u)
    return u, tail

def units(scene_dir):
    out = []
    for fn in sorted(os.listdir(scene_dir)):
        if not fn.startswith('gri_'): continue
        sc = Scene.load(open(os.path.join(scene_dir, fn), 'rb').read())
        key = fn[len('gri_ano03_'):-4]
        speaker = None
        for i, (t, s) in enumerate(sc.lines):
            u = s.decode('cp932')
            if t == 0x21: speaker = u; continue
            if t == 0x20:
                ja, tail = clean_ja(u)
                if ja.strip():
                    out.append({"id": f"{key}:{i:04d}", "speaker": speaker, "ja": ja, "ja_len": len(ja)})
                speaker = None
            elif t == 0x02: speaker = None
    return out

if __name__ == '__main__':
    scene_dir, outdir = sys.argv[1], sys.argv[2]
    per = int(sys.argv[3]) if len(sys.argv) > 3 else 115
    us = units(scene_dir); os.makedirs(outdir, exist_ok=True)
    for b in range(0, len(us), per):
        with open(os.path.join(outdir, f"in-{b // per:03d}.json"), 'w', encoding='utf-8') as f:
            json.dump(us[b:b + per], f, ensure_ascii=False, indent=1)
    with open(os.path.join(outdir, 'all-units.json'), 'w', encoding='utf-8') as f:
        json.dump(us, f, ensure_ascii=False, indent=1)
    print('units', len(us), 'batches', (len(us) + per - 1) // per)
