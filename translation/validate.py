"""檢查譯文檔 out-NNN.json（或 fix 檔）是否符合規則。用法：python validate.py out-000.json [out-001.json ...]
全部通過 → 結尾印 ALL OK，回傳碼 0。
"""
import sys, os, json, re, glob

HERE = os.path.dirname(os.path.abspath(__file__))
HARD_MAX = 90           # 一則訊息的上限（全形字數；遊戲訊息框約 3 行 × 30 字）
EXTRA_OK = set('—─―♪～…‧·•☆★♥○●◎×÷＝％＃＆＊＠')
BAD = set('[]\\@#{}<>`|')
KANA = re.compile(r'[぀-ヿㇰ-ㇿｦ-ﾟ]')
SIMP_HINT = set('这们说时为个们会来过还没对给问让觉见话经么从两样')  # 常見簡體字（cp950 也無法編碼，雙重保險）

def load_in(batch_file):
    n = os.path.basename(batch_file)
    m = re.search(r'(\d{3})', n)
    src = os.path.join(HERE, f'in-{m.group(1)}.json')
    return json.load(open(src, encoding='utf-8'))

def width(s):
    return sum(1 if ord(c) < 0x80 else 2 for c in s) / 2

def check(path):
    errs = []
    try:
        out = json.load(open(path, encoding='utf-8'))
    except Exception as e:
        return [f'{path}: 不是合法 UTF-8 JSON：{e}']
    src = load_in(path)
    if [o.get('id') for o in out] != [s['id'] for s in src]:
        errs.append(f'{path}: id 列表與 in 檔不一致（數量 {len(out)} vs {len(src)}，順序須相同）')
        sd = {s['id']: s for s in src}
    else:
        sd = {s['id']: s for s in src}
    for o in out:
        i, zh = o.get('id'), o.get('zh')
        s = sd.get(i)
        if s is None: continue
        if not isinstance(zh, str) or not zh.strip():
            errs.append(f'{i}: 譯文空白'); continue
        if '?' in zh and '?' not in s['ja'] and '？' not in zh and zh.count('?') > 2:
            errs.append(f'{i}: 疑似編碼遺失（大量 ?）')
        if KANA.search(zh): errs.append(f'{i}: 殘留日文假名：{zh}')
        bad = [c for c in zh if c in BAD]
        if bad: errs.append(f'{i}: 不可使用字元 {bad}')
        if any(c in SIMP_HINT for c in zh): errs.append(f'{i}: 疑似簡體字：{zh}')
        for c in zh:
            if ord(c) < 0x80 or c in EXTRA_OK: continue
            try: c.encode('cp950')
            except UnicodeEncodeError: errs.append(f'{i}: 非繁體常用字（cp950 無此字）「{c}」')
        ja = s['ja']
        for a, b in (('「', '」'), ('『', '』'), ('（', '）')):
            if ja.startswith(a) and ja.endswith(b) and not (zh.startswith(a) and zh.endswith(b)):
                errs.append(f'{i}: 原文以 {a}…{b} 包住，譯文也必須以 {a} 開頭、{b} 結尾')
        w = width(zh)
        lim = min(HARD_MAX, max(s['ja_len'] + 8, s['ja_len'] * 1.3))
        if w > lim: errs.append(f'{i}: 太長 {w:.0f} 字（上限 {lim:.0f}，原文 {s["ja_len"]} 字）')
    return errs

if __name__ == '__main__':
    files = []
    for a in sys.argv[1:]: files += sorted(glob.glob(a)) or [a]
    total = 0
    for f in files:
        e = check(f); total += len(e)
        print(f'{f}: {"ok" if not e else str(len(e)) + " 個問題"}')
        for x in e[:200]: print('   ', x)
    if total == 0 and files: print('ALL OK')
    sys.exit(1 if total else 0)
