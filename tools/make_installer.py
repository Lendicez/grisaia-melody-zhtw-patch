r"""Windows 本機：以內建 .NET Framework csc.exe 編譯安裝程式，並做自我測試。

python make_installer.py --payload payload.json --dll version.dll --version 0.1.0 --orig PRISTINE_DIR --out OUT_DIR [--expect EXPECT_DIR]
  * 產生 Version.cs → csc 編譯 <OUT>\GrisaiaMelody-zhTW-Patch-<版號>.exe（內嵌 payload.json、version.dll）
  * 自我測試：把 PRISTINE_DIR 的 GrisaiaAno3.exe、scene.int、config.int、fes.int 複製到 <OUT>\selftest\game，
    /status → /install → （若給 --expect：比對解開後每個修改檔內容與 Python 建置結果一致）→ /install 再一次（應拒絕或維持）→ /uninstall（核對還原為原版）
"""
import argparse, glob, hashlib, json, os, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / 'installer'

def find_csc():
    c = sorted(glob.glob(r'C:\Windows\Microsoft.NET\Framework64\v4*\csc.exe')) or sorted(glob.glob(r'C:\Windows\Microsoft.NET\Framework\v4*\csc.exe'))
    if not c: raise SystemExit('找不到 .NET Framework 4 csc.exe')
    return c[-1]

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def run(exe, *args):
    r = subprocess.run([str(exe), *args, '/ignore-running'], capture_output=True, text=True, encoding='utf-8', errors='replace')
    print('>', ' '.join(args), 'rc', r.returncode); print(r.stdout.strip()); return r

def main():
    ap = argparse.ArgumentParser()
    for k in ('--payload', '--dll', '--version', '--orig', '--out'): ap.add_argument(k, required=True)
    ap.add_argument('--expect')
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    build = out / 'build'; build.mkdir(exist_ok=True)
    v = a.version
    (build / 'Version.cs').write_text('namespace GrisaiaZhTW { static partial class Ver { public const string Assembly = "%s.0"; } }\n' % v, 'utf-8')
    shutil.copy2(a.payload, build / 'payload.json'); shutil.copy2(a.dll, build / 'version.dll')
    exe = out / f'GrisaiaMelody-zhTW-Patch-{v}.exe'
    cmd = [find_csc(), '/nologo', '/target:winexe', '/platform:anycpu', '/optimize+', '/codepage:65001',
           f'/out:{exe}', '/r:System.Windows.Forms.dll', '/r:System.Drawing.dll',
           f'/resource:{build / "payload.json"},payload.json', f'/resource:{build / "version.dll"},version.dll',
           str(SRC / 'Setup.cs'), str(SRC / 'Cs2.cs'), str(SRC / 'BfTables.cs'), str(build / 'Version.cs')]
    if (SRC / 'app.manifest').exists(): cmd.insert(5, f'/win32manifest:{SRC / "app.manifest"}')
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode: raise SystemExit('csc 失敗：\n' + r.stdout[-4000:] + r.stderr[-2000:])
    print('built', exe, sha(exe))

    st = out / 'selftest' / 'game'
    if st.parent.exists(): shutil.rmtree(st.parent)
    st.mkdir(parents=True)
    arcs = list(json.load(open(a.payload, encoding='utf-8'))['archives'])
    names = ['GrisaiaAno3.exe'] + arcs
    for n in names: shutil.copy2(Path(a.orig) / n, st / n)
    res = {'exe': exe.name, 'sha256': sha(exe), 'steps': []}
    ok = True
    r = run(exe, '/status', str(st)); ok &= 'state=Original' in r.stdout; res['steps'].append(['status', r.stdout])
    r = run(exe, '/install', str(st)); ok &= r.returncode == 0 and 'state=Installed' in r.stdout; res['steps'].append(['install', r.stdout])
    if a.expect:
        sys.path.insert(0, str(HERE))
        from cs2int import Archive, pass_from_exe, key_from_pass
        from cst import Scene
        import zlib, struct
        key = key_from_pass(pass_from_exe(str(st / 'GrisaiaAno3.exe')))
        for n in arcs:
            A, B = Archive(str(st / n), key), Archive(str(Path(a.expect) / n), key)
            closers = (A.f, B.f)
            for (en, _, _), (bn, _, _) in zip(A.entries, B.entries):
                da, db = A.read(en), B.read(bn)
                if en.endswith('.cst'): same = Scene.load(da).build_body() == Scene.load(db).build_body()
                elif en.endswith('.fes'): same = zlib.decompress(da[16:]) == zlib.decompress(db[16:])
                else: same = da == db
                if not same: ok = False; print('MISMATCH', n, en)
            for f in closers: f.close()
        res['steps'].append(['compare', 'done'])
    r = run(exe, '/install', str(st)); res['steps'].append(['install-again', r.stdout])
    r = run(exe, '/uninstall', str(st)); ok &= r.returncode == 0
    for n in names[1:]: ok &= sha(st / n) == sha(Path(a.orig) / n)
    for n in ('version.dll', 'zhtw_map.bin', 'zhtw.ini', 'language.txt'): ok &= not (st / n).exists()
    res['steps'].append(['uninstall', r.stdout]); res['selftest_ok'] = bool(ok)
    (out / 'release.json').write_text(json.dumps(res, ensure_ascii=False, indent=1), 'utf-8')
    print('SELFTEST', 'OK' if ok else 'FAILED')
    sys.exit(0 if ok else 1)

if __name__ == '__main__':
    main()
