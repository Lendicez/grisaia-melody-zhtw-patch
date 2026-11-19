"""編譯 version.dll（32 位元）。需要 `pip install ziglang`（以 zig cc 交叉編譯，Linux／Windows 皆可）。
python hook/build.py  → hook/build/version.dll
"""
import subprocess, sys
from pathlib import Path
H = Path(__file__).resolve().parent
MH = H / 'third_party' / 'minhook'
(H / 'build').mkdir(exist_ok=True)
cmd = [sys.executable, '-m', 'ziglang', 'cc', '-target', 'x86-windows-gnu', '-O2', '-shared', '-s',
       '-o', str(H / 'build' / 'version.dll'), str(H / 'zhtw_hook.c'), str(H / 'version.def'),
       str(MH / 'src' / 'hook.c'), str(MH / 'src' / 'buffer.c'), str(MH / 'src' / 'trampoline.c'), str(MH / 'src' / 'hde' / 'hde32.c'),
       '-I' + str(MH / 'include'), '-lgdi32', '-luser32']
r = subprocess.run(cmd)
sys.exit(r.returncode)
