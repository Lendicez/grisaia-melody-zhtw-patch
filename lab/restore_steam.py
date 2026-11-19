# 還原 Steam 資料夾：備份原檔覆蓋回去、移除測試加入的檔案，最後與 lab 的原版比對
import json, shutil, hashlib
from pathlib import Path
G = Path(r"D:\SteamLibrary\steamapps\common\The Melody of Grisaia"); B = G / "_zhTW_backup"
P = Path(r"C:\GameDev\grisaia-melody-lab\pristine-ja")
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()[:16]
ARCH = ("scene.int", "config.int", "fes.int", "image.int")
for n in ARCH:
    src = B / n if (B / n).exists() else P / n
    if (G / n).exists() and sha(G / n) == sha(src):
        print("ok", n); continue
    shutil.copy2(src, G / n); print("restore", n, "from", src.parent.name)
added = set(("version.dll", "zhtw.ini", "zhtw_map.bin", "zhtw_hook.log", "language.txt"))
if (B / "added.json").exists():
    added |= set(json.loads((B / "added.json").read_text(encoding="utf-8")))
for n in sorted(added):
    p = G / n
    if p.exists():
        try: p.unlink(); print("removed", n)
        except Exception as e: print("FAILED remove", n, e)
bad = [n for n in ARCH + ("GrisaiaAno3.exe",) if sha(G / n) != sha(P / n)]
if bad:
    print("MISMATCH vs pristine:", bad, "- backup kept")
else:
    shutil.rmtree(B, ignore_errors=True); print("all pristine; backup dir removed:", not B.exists())
