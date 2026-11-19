# 還原 Steam 資料夾：備份原檔覆蓋回去、移除測試加入的檔案（version.dll、zhtw.ini、zhtw_map.bin、zhtw_hook.log）
import json, shutil, hashlib
from pathlib import Path
G = Path(r"D:\SteamLibrary\steamapps\common\The Melody of Grisaia"); B = G / "_zhTW_backup"
P = Path(r"C:\GameDev\grisaia-melody-lab\pristine-ja")
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()[:16]
for n in ("scene.int", "config.int", "fes.int"):
    src = B / n if (B / n).exists() else P / n
    shutil.copy2(src, G / n); print("restore", n, sha(G / n), "pristine", sha(P / n))
for n in ("version.dll", "zhtw.ini", "zhtw_map.bin", "zhtw_hook.log"):
    p = G / n
    if p.exists():
        try: p.unlink(); print("removed", n)
        except Exception as e: print("FAILED remove", n, e)
shutil.rmtree(B, ignore_errors=True); print("backup dir removed:", not B.exists())
