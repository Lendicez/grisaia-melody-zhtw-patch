"""language.txt（CatSystem2 執行檔字串表）工具。
格式：'//日文原文' 註解行、'$xxxx-xxxx$' 編號行、其後到空行前為譯文（可多行）；$nr$＝不變換、$empty$＝空字串。
  python lang_tool.py extract EN_language.txt OUTDIR [每批]  → lang-in-NNN.json（id, ja, en, has）（lab 用，含原文）
  （組裝由 build_patch.py 讀 lang-out-*.json 產生 language.txt）
"""
import json, os, re, sys

def parse(path):
    lines = open(path, 'rb').read().decode('utf-8-sig').split('\r\n')
    ents = []; i = 0; comment = []
    while i < len(lines):
        ln = lines[i]
        m = re.fullmatch(r'\$([0-9]{4}-[0-9]{4})\$', ln)
        if m:
            val = []; i += 1
            while i < len(lines) and lines[i] != '' and not lines[i].startswith('//') and not re.fullmatch(r'\$[0-9]{4}-[0-9]{4}\$', lines[i]):
                val.append(lines[i]); i += 1
            ja = comment[-1] if comment else ''
            ents.append({'id': m.group(1), 'ja': ja, 'en': '\n'.join(val)})
            comment = []; continue
        if ln.startswith('//'): comment.append(ln[2:])
        elif ln == '': pass
        i += 1
    return ents

def header(path):
    s = open(path, 'rb').read().decode('utf-8-sig').split('\r\n')
    return s[:3]

if __name__ == '__main__':
    if sys.argv[1] == 'extract':
        ents = parse(sys.argv[2]); out = sys.argv[3]; per = int(sys.argv[4]) if len(sys.argv) > 4 else 300
        os.makedirs(out, exist_ok=True)
        todo = [e for e in ents if e['ja'].strip()]   # $nr$（沿用內建日文）也一併翻譯，否則會顯示日文
        for b in range(0, len(todo), per):
            json.dump(todo[b:b + per], open(os.path.join(out, f'lang-in-{b // per:03d}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print('entries', len(ents), 'to translate', len(todo), 'nr', len(ents) - len(todo))
