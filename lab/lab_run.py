r"""Grisaia Melody zh-TW lab runner (Windows).  只在 lab 副本執行，不碰 Steam 原安裝。

python lab_run.py --run-id R1 --steps steps.json [--payload DIR] [--fresh]
  * lab 遊戲：C:\GameDev\grisaia-melody-lab\game（第一次自動從 Steam 安裝資料夾複製；--fresh 重新複製 .int/.exe）
  * payload：把 DIR 內所有檔案覆蓋進 lab 遊戲（version.dll、zhtw.ini、zhtw_map.bin、*.int …）
  * steps：[{"wait":秒}, {"shot":"名"}, {"click":[x,y]}, {"key":"RETURN"|"ESCAPE"|"SPACE"|"CONTROL"...}, {"wheel":-1}]
    座標為遊戲視窗 client 區（1280x720 基準，會依實際 client 大小縮放）
  * 結果：C:\GameDev\grisaia-melody-lab\runs\<run-id>\ （截圖、zhtw_hook.log、report.json）
"""
import argparse, ctypes, ctypes.wintypes as W, json, os, shutil, subprocess, sys, time
from pathlib import Path

STEAM_GAME = Path(r"D:\SteamLibrary\steamapps\common\The Melody of Grisaia")
LAB = Path(r"C:\GameDev\grisaia-melody-lab")
GAME = LAB / "game"
EXE = "GrisaiaAno3.exe"
APPID = "464500"

user32 = ctypes.windll.user32
try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception: user32.SetProcessDPIAware()

def ensure_game(fresh):
    if GAME.exists() and not fresh: return
    GAME.mkdir(parents=True, exist_ok=True)
    for p in STEAM_GAME.iterdir():
        if p.is_file(): shutil.copy2(p, GAME / p.name)
        elif p.is_dir(): shutil.copytree(p, GAME / p.name, dirs_exist_ok=True)

k32 = ctypes.windll.kernel32

def image_of(pid):
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h: return ""
    buf = ctypes.create_unicode_buffer(1024); n = W.DWORD(1024)
    ok = k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)); k32.CloseHandle(h)
    return buf.value if ok else ""

def lab_pids():
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {EXE}", "/FO", "CSV", "/NH"], capture_output=True, text=True, errors="replace").stdout
    pids = []
    for line in out.splitlines():
        parts = line.strip('"').split('","')
        if len(parts) > 1 and parts[1].isdigit(): pids.append(int(parts[1]))
    return [p for p in pids if image_of(p).lower() == str(GAME / EXE).lower()]

def windows():
    res = []
    @ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    def cb(h, l):
        if user32.IsWindowVisible(h):
            p = W.DWORD(); user32.GetWindowThreadProcessId(h, ctypes.byref(p))
            b = ctypes.create_unicode_buffer(256); user32.GetWindowTextW(h, b, 256)
            res.append((h, p.value, b.value))
        return True
    user32.EnumWindows(cb, 0)
    return res

def click_rightmost_button(hwnd):
    """起動時「表示モード選擇」對話框：一律按右邊按鈕（視窗化）。"""
    found = []
    @ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    def cb(h, l):
        cls = ctypes.create_unicode_buffer(64); user32.GetClassNameW(h, cls, 64)
        if cls.value.lower() == "button":
            r = W.RECT(); user32.GetWindowRect(h, ctypes.byref(r)); found.append((r.left, h))
        return True
    user32.EnumChildWindows(hwnd, cb, 0)
    if len(found) >= 2:
        user32.PostMessageW(max(found)[1], 0x00F5, 0, 0)  # BM_CLICK
        return True
    return False

def find_window(pids, timeout=60, rep=None):
    t0 = time.time()
    while time.time() - t0 < timeout:
        pids = set(pids) | set(lab_pids())
        for h, pid, title in windows():
            if pid not in pids: continue
            r = W.RECT(); user32.GetClientRect(h, ctypes.byref(r))
            if r.right > 500: return h
            if click_rightmost_button(h):
                if rep is not None: rep["events"].append("display-mode dialog -> right button (windowed)")
                time.sleep(2)
        time.sleep(0.5)
    return None

def client_box(h):
    r = W.RECT(); user32.GetClientRect(h, ctypes.byref(r))
    pt = W.POINT(0, 0); user32.ClientToScreen(h, ctypes.byref(pt))
    return pt.x, pt.y, r.right, r.bottom

def fg(h):
    user32.ShowWindow(h, 9)
    fgw = user32.GetForegroundWindow()
    t1 = user32.GetWindowThreadProcessId(fgw, None); t2 = ctypes.windll.kernel32.GetCurrentThreadId()
    user32.AttachThreadInput(t2, t1, True); user32.SetForegroundWindow(h); user32.AttachThreadInput(t2, t1, False)

VK = {"RETURN": 0x0D, "ESCAPE": 0x1B, "SPACE": 0x20, "CONTROL": 0x11, "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27, "F1": 0x70}

def click(h, x, y):
    bx, by, bw, bh = client_box(h)
    sx, sy = bx + int(x * bw / 1280), by + int(y * bh / 720)
    user32.SetCursorPos(sx, sy); time.sleep(0.08)
    user32.mouse_event(2, 0, 0, 0, 0); time.sleep(0.05); user32.mouse_event(4, 0, 0, 0, 0)

def key(name):
    v = VK[name]; user32.keybd_event(v, 0, 0, 0); time.sleep(0.05); user32.keybd_event(v, 0, 2, 0)

def shot(h, path):
    from PIL import Image
    gdi32 = ctypes.windll.gdi32
    r = W.RECT(); user32.GetClientRect(h, ctypes.byref(r)); w, hh = r.right, r.bottom
    wr = W.RECT(); user32.GetWindowRect(h, ctypes.byref(wr))
    pt = W.POINT(0, 0); user32.ClientToScreen(h, ctypes.byref(pt))
    ox, oy = pt.x - wr.left, pt.y - wr.top
    ww, wh = wr.right - wr.left, wr.bottom - wr.top
    hdc = user32.GetWindowDC(h); mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, ww, wh); gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(h, mdc, 2)  # PW_RENDERFULLCONTENT
    class BIH(ctypes.Structure):
        _fields_ = [("biSize", W.DWORD), ("biWidth", W.LONG), ("biHeight", W.LONG), ("biPlanes", W.WORD), ("biBitCount", W.WORD),
                    ("biCompression", W.DWORD), ("biSizeImage", W.DWORD), ("biXPelsPerMeter", W.LONG), ("biYPelsPerMeter", W.LONG),
                    ("biClrUsed", W.DWORD), ("biClrImportant", W.DWORD)]
    bi = BIH(); bi.biSize = ctypes.sizeof(BIH); bi.biWidth = ww; bi.biHeight = -wh; bi.biPlanes = 1; bi.biBitCount = 32
    buf = ctypes.create_string_buffer(ww * wh * 4)
    gdi32.GetDIBits(mdc, bmp, 0, wh, buf, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp); gdi32.DeleteDC(mdc); user32.ReleaseDC(h, hdc)
    im = Image.frombuffer("RGB", (ww, wh), buf, "raw", "BGRX", 0, 1)
    im.crop((ox, oy, ox + w, oy + hh)).save(path)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True); ap.add_argument("--steps", required=True)
    ap.add_argument("--payload"); ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--restore", action="store_true", help="先還原原檔並移除 payload")
    ap.add_argument("--steam", action="store_true", help="直接在 Steam 安裝資料夾測試（原檔備份到 _zhTW_backup），經 Steam 啟動")
    a = ap.parse_args()
    global GAME
    if a.steam: GAME = STEAM_GAME
    out = LAB / "runs" / a.run_id; out.mkdir(parents=True, exist_ok=True)
    rep = {"run_id": a.run_id, "events": []}
    if not a.steam: ensure_game(a.fresh)
    bk = GAME / "_zhTW_backup"
    if a.restore:
        added = json.loads((bk / "added.json").read_text("utf-8")) if (bk / "added.json").exists() else []
        for n in added: (GAME / n).unlink(missing_ok=True)
        if bk.exists():
            for p in bk.iterdir():
                if p.name != "added.json": shutil.copy2(p, GAME / p.name)
        rep["events"].append(f"restored; removed {added}")
    if a.payload:
        bk.mkdir(exist_ok=True)
        added = json.loads((bk / "added.json").read_text("utf-8")) if (bk / "added.json").exists() else []
        for p in Path(a.payload).iterdir():
            if not p.is_file(): continue
            dst = GAME / p.name
            if dst.exists() and not (bk / p.name).exists() and p.name not in added: shutil.copy2(dst, bk / p.name)
            elif not dst.exists() and p.name not in added: added.append(p.name)
            shutil.copy2(p, dst); rep["events"].append("payload " + p.name)
        (bk / "added.json").write_text(json.dumps(added), "utf-8")
    if not a.steam: (GAME / "steam_appid.txt").write_text(APPID)
    for p in lab_pids():
        r = subprocess.run(["taskkill", "/PID", str(p), "/T", "/F"], capture_output=True, text=True, errors="replace")
        rep["events"].append(f"prekill {p}: {r.returncode} {r.stdout.strip()} {r.stderr.strip()}")
    time.sleep(2)
    log = GAME / "zhtw_hook.log"
    try:
        if log.exists(): log.unlink()
    except OSError as e: rep["events"].append(f"log unlink failed: {e}")
    steps = json.loads(Path(a.steps).read_text("utf-8"))
    if a.steam:
        os.startfile(f"steam://rungameid/{APPID}")
        class _P: pid = -1
        proc = _P()
    else:
        proc = subprocess.Popen([str(GAME / EXE)], cwd=str(GAME))
    rep["pid"] = proc.pid
    h = None
    try:
        h = find_window([proc.pid], 90, rep)
        rep["window"] = bool(h)
        if not h: raise RuntimeError("找不到遊戲視窗")
        fg(h); n = 0
        for st in steps:
            if not user32.IsWindow(h): rep["events"].append("window closed"); break
            if "wait" in st: time.sleep(st["wait"])
            elif "shot" in st:
                n += 1; p = out / f"{n:02d}-{st['shot']}.png"; fg(h); time.sleep(0.3); shot(h, p); rep["events"].append("shot " + p.name)
            elif "click" in st: fg(h); click(h, *st["click"])
            elif "key" in st: fg(h); key(st["key"])
            elif "clicks" in st:
                for _ in range(st["clicks"]): fg(h); click(h, *st.get("at", [640, 600])); time.sleep(st.get("gap", 1.0))
    except Exception as e:
        rep["error"] = f"{type(e).__name__}: {e}"
    finally:
        rep["pids_at_end"] = lab_pids()
        for p in set(rep["pids_at_end"]) | ({proc.pid} if proc.pid > 0 else set()):
            r = subprocess.run(["taskkill", "/PID", str(p), "/T", "/F"], capture_output=True, text=True, errors="replace")
            rep["events"].append(f"kill {p}: {r.returncode} {r.stdout.strip()} {r.stderr.strip()}")
        time.sleep(1)
        if log.exists(): shutil.copy2(log, out / "zhtw_hook.log")
        (out / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), "utf-8")
        print(json.dumps(rep, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
