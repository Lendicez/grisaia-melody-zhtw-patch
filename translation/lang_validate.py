"""檢查 lang-out-NNN.json：python lang_validate.py lang-out-000.json ...  全過印 ALL OK。"""
import sys, os, re, json, glob
HERE = os.path.dirname(os.path.abspath(__file__))
KANA = re.compile(r'[぀-ヿｦ-ﾟ]')
PH = re.compile(r'%[-0-9.]*[sdcxXuf%]|\\[nrt]')
def acc(s): return re.findall(r'&[A-Za-z0-9]', s)
def width(s): return sum(1 if ord(c) < 0x80 else 2 for c in s) / 2
def check(path):
    errs = []; out = json.load(open(path, encoding='utf-8'))
    src = json.load(open(os.path.join(HERE, os.path.basename(path).replace('lang-out', 'lang-in')), encoding='utf-8'))
    if [o.get('id') for o in out] != [e['id'] for e in src]: errs.append('id 列表與 lang-in 不一致（數量、順序須相同；編號可重複，照 lang-in 逐筆對應）')
    for o, e in zip(out, src):
        zh = o.get('zh')
        if o.get('id') != e['id']: continue
        if not isinstance(zh, str): errs.append(f"{o['id']}: zh 缺漏"); continue
        if KANA.search(zh): errs.append(f"{o['id']}: 殘留假名：{zh}")
        ref = e['ja']
        if PH.findall(zh) != PH.findall(ref): errs.append(f"{o['id']}: 格式符號 {PH.findall(ref)} 必須原樣保留且順序相同：{zh}")
        if [a.upper() for a in acc(zh)] != [a.upper() for a in acc(ref)]: errs.append(f"{o['id']}: 快速鍵 {acc(ref)} 須保留（例：結束遊戲(&X)）：{zh}")
        for c in zh:
            if ord(c) < 0x80 or c in '—─…～・‧': continue
            try: c.encode('cp950')
            except UnicodeEncodeError: errs.append(f"{o['id']}: 非繁體常用字「{c}」")
        lim = max(len(ref) * 1.3 + 2, 6)
        if width(zh) > lim: errs.append(f"{o['id']}: 太長 {width(zh):.0f}（上限 {lim:.0f}，原文 {len(ref)} 字）")
    return errs
if __name__ == '__main__':
    files = [f for a in sys.argv[1:] for f in (sorted(glob.glob(a)) or [a])]; total = 0
    for f in files:
        e = check(f); total += len(e); print(f, 'ok' if not e else f'{len(e)} 個問題')
        for x in e[:200]: print('   ', x)
    if files and not total: print('ALL OK')
    sys.exit(1 if total else 0)
