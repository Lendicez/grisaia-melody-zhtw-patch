// ---------------------------------------------------------------- 視窗化強化（[window] enable=1）
// 引擎以 Direct3D 9 視窗模式繪製固定 1280×720 的後緩衝，Present 時由顯示卡拉伸到視窗內容區。
// 這裡做的事：
//   1. 視窗加上可拉動邊框與最大化按鈕；拖拉時鎖定 16:9。
//   2. 內容區大小與引擎設定的尺寸（g_eng_w×g_eng_h）不同時（自由縮放、最大化、無邊框全螢幕），
//      Present 改畫到置中的等比區域，其餘塗黑；尺寸變化不轉給引擎（否則它會把視窗彈回原尺寸）；
//      滑鼠座標換算回引擎尺寸，黑邊上的點擊直接丟棄。
//   3. 引擎自己的「全螢幕」（Alt+Enter／設定頁）不再切換桌面解析度，改成蓋滿目前螢幕的無邊框視窗。
//   4. 引擎主動改視窗大小（原版的視窗大小選項）一律放行，並結束自由縮放／最大化。
// g_win_enable 宣告於 zhtw_hook.c 前段

#define WIN_ADD_STYLE (WS_THICKFRAME | WS_MAXIMIZEBOX)
#define WM_ZH_RESTORE (WM_APP + 0x5A1)

typedef void *(WINAPI *wD3DC9_t)(UINT);
typedef HRESULT (WINAPI *wCDev_t)(void *, UINT, int, HWND, DWORD, void *, void **);
typedef HRESULT (WINAPI *wReset_t)(void *, void *);
typedef HRESULT (WINAPI *wPresent_t)(void *, const RECT *, const RECT *, HWND, const RGNDATA *);
typedef BOOL (WINAPI *wSWP_t)(HWND, HWND, int, int, int, int, UINT);
typedef BOOL (WINAPI *wMW_t)(HWND, int, int, int, int, BOOL);
typedef LONG (WINAPI *wSWLA_t)(HWND, int, LONG);
typedef BOOL (WINAPI *wAWR_t)(LPRECT, DWORD, BOOL);
typedef BOOL (WINAPI *wAWRE_t)(LPRECT, DWORD, BOOL, DWORD);
typedef BOOL (WINAPI *wGCR_t)(HWND, LPRECT);
typedef BOOL (WINAPI *wPT_t)(HWND, LPPOINT);
typedef BOOL (WINAPI *wSW_t)(HWND, int);
typedef BOOL (WINAPI *wSWPL_t)(HWND, const WINDOWPLACEMENT *);
typedef LONG (WINAPI *wCDSA_t)(void *, DWORD);
typedef LONG (WINAPI *wCDSEA_t)(LPCSTR, void *, HWND, DWORD, LPVOID);
static wD3DC9_t w_D3DC9; static wCDev_t w_CDev; static wReset_t w_Reset; static wPresent_t w_Present;
static wSWP_t w_SWP; static wMW_t w_MW; static wSWLA_t w_SWLA; static wAWR_t w_AWR; static wAWRE_t w_AWRE;
static wSW_t w_SW; static wSWPL_t w_SWPL;
static wGCR_t w_GCR; static wPT_t w_S2C, w_C2S; static wCDSA_t w_CDSA; static wCDSEA_t w_CDSEA;

static HWND g_w_main; static WNDPROC g_w_proc;
static volatile int g_eng_w, g_eng_h;     // 引擎認定的內容區尺寸
static volatile int g_border;             // 無邊框全螢幕中
static RECT g_mon;                        // 無邊框全螢幕使用的螢幕
static WINDOWPLACEMENT g_saved_wp; static int g_have_saved;

#define WLOG(...) do { if (g_diag_wnd) logf(__VA_ARGS__); } while (0)

static int from_game(void *ret) { return from_exe(ret); }

// 內容區與引擎尺寸不同 → 需要縮放
static int w_scaled(RECT *cr_out) {
    RECT cr; if (!g_w_main || !w_GCR(g_w_main, &cr)) return 0;
    if (cr_out) *cr_out = cr;
    if (g_eng_w <= 0 || g_eng_h <= 0 || cr.right <= 0 || cr.bottom <= 0) return 0;
    return cr.right != g_eng_w || cr.bottom != g_eng_h;
}
// 置中的等比顯示區（內容區座標）
static void w_dest(const RECT *cr, RECT *d) {
    int cw = cr->right, ch = cr->bottom;
    long long a = (long long)cw * g_eng_h, b = (long long)ch * g_eng_w;
    int dw, dh;
    if (a >= b) { dh = ch; dw = (int)(((long long)ch * g_eng_w + g_eng_h / 2) / g_eng_h); }
    else { dw = cw; dh = (int)(((long long)cw * g_eng_h + g_eng_w / 2) / g_eng_w); }
    d->left = (cw - dw) / 2; d->top = (ch - dh) / 2; d->right = d->left + dw; d->bottom = d->top + dh;
}
// 實際內容區座標 → 引擎座標；回傳是否落在顯示區內
static int w_to_eng(int x, int y, int *ox, int *oy) {
    RECT cr, d; if (!w_scaled(&cr)) { *ox = x; *oy = y; return 1; }
    w_dest(&cr, &d);
    int dw = d.right - d.left, dh = d.bottom - d.top; if (dw <= 0 || dh <= 0) { *ox = x; *oy = y; return 1; }
    int in = x >= d.left && x < d.right && y >= d.top && y < d.bottom;
    long long ex = (long long)(x - d.left) * g_eng_w / dw, ey = (long long)(y - d.top) * g_eng_h / dh;
    if (ex < 0) ex = 0; if (ex > g_eng_w - 1) ex = g_eng_w - 1;
    if (ey < 0) ey = 0; if (ey > g_eng_h - 1) ey = g_eng_h - 1;
    *ox = (int)ex; *oy = (int)ey; return in;
}
static void w_from_eng(int x, int y, int *ox, int *oy) {
    RECT cr, d; if (!w_scaled(&cr)) { *ox = x; *oy = y; return; }
    w_dest(&cr, &d);
    *ox = d.left + (int)((long long)x * (d.right - d.left) / g_eng_w);
    *oy = d.top + (int)((long long)y * (d.bottom - d.top) / g_eng_h);
}
static DWORD w_fix_style(DWORD st) {
    if ((st & WS_CAPTION) == WS_CAPTION && !(st & WS_POPUP)) st |= WIN_ADD_STYLE;
    return st;
}
static void w_update_eng(void) {
    RECT cr; if (g_w_main && w_GCR(g_w_main, &cr) && cr.right > 0 && cr.bottom > 0) { g_eng_w = cr.right; g_eng_h = cr.bottom; }
    WLOG("[win] engine size %dx%d\n", g_eng_w, g_eng_h);
}

// ---------- Direct3D 9
static HRESULT WINAPI w_h_Present(void *dev, const RECT *s, const RECT *dr, HWND w, const RGNDATA *rg) {
    RECT cr, d;
    if (dr || w || !w_scaled(&cr)) return w_Present(dev, s, dr, w, rg);
    w_dest(&cr, &d);
    HRESULT r = w_Present(dev, s, &d, w, rg);
    HDC dc = GetDC(g_w_main);
    if (dc) {
        HBRUSH b = (HBRUSH)GetStockObject(BLACK_BRUSH);
        RECT t;
        if (d.top > 0) { SetRect(&t, 0, 0, cr.right, d.top); FillRect(dc, &t, b); }
        if (d.bottom < cr.bottom) { SetRect(&t, 0, d.bottom, cr.right, cr.bottom); FillRect(dc, &t, b); }
        if (d.left > 0) { SetRect(&t, 0, d.top, d.left, d.bottom); FillRect(dc, &t, b); }
        if (d.right < cr.right) { SetRect(&t, d.right, d.top, cr.right, d.bottom); FillRect(dc, &t, b); }
        ReleaseDC(g_w_main, dc);
    }
    return r;
}
static HRESULT WINAPI w_h_Reset(void *dev, void *pp) {
    HRESULT r = w_Reset(dev, pp); WLOG("[win] Reset -> %08lx\n", (unsigned long)r); return r;
}
static HRESULT WINAPI w_h_CDev(void *d3d, UINT ad, int type, HWND focus, DWORD beh, void *pp, void **out) {
    HRESULT r = w_CDev(d3d, ad, type, focus, beh, pp, out);
    WLOG("[win] CreateDevice -> %08lx\n", (unsigned long)r);
    if (r == 0 && out && *out && !w_Present) {
        void **vt = *(void ***)*out;
        MH_CreateHook(vt[16], (void *)w_h_Reset, (void **)&w_Reset); MH_EnableHook(vt[16]);
        MH_CreateHook(vt[17], (void *)w_h_Present, (void **)&w_Present); MH_EnableHook(vt[17]);
    }
    return r;
}
static void *WINAPI w_h_D3DC9(UINT v) {
    void *d = w_D3DC9(v);
    if (d && !w_CDev) { void **vt = *(void ***)d; MH_CreateHook(vt[16], (void *)w_h_CDev, (void **)&w_CDev); MH_EnableHook(vt[16]); }
    return d;
}

// ---------- 無邊框全螢幕
static void w_enter_border(void) {
    if (g_border) return;
    g_saved_wp.length = sizeof g_saved_wp; g_have_saved = GetWindowPlacement(g_w_main, &g_saved_wp);
    MONITORINFO mi; mi.cbSize = sizeof mi;
    if (GetMonitorInfoA(MonitorFromWindow(g_w_main, MONITOR_DEFAULTTONEAREST), &mi)) g_mon = mi.rcMonitor;
    else SetRect(&g_mon, 0, 0, GetSystemMetrics(SM_CXSCREEN), GetSystemMetrics(SM_CYSCREEN));
    g_border = 1;
    WLOG("[win] enter borderless monitor=%ld,%ld-%ld,%ld\n", g_mon.left, g_mon.top, g_mon.right, g_mon.bottom);
}
static void w_leave_border(void) {
    if (!g_border) return;
    g_border = 0;
    WLOG("[win] leave borderless\n");
    PostMessageA(g_w_main, WM_ZH_RESTORE, 0, 0);   // 等引擎自己的還原動作做完，再回到使用者原本的位置／大小
}
static LONG WINAPI w_h_CDSA(void *dm, DWORD fl) {
    if (from_game(__builtin_return_address(0))) {
        WLOG("[win] ChangeDisplaySettingsA(%p, %lx) blocked\n", dm, (unsigned long)fl);
        if (!dm) w_leave_border();
        return DISP_CHANGE_SUCCESSFUL;
    }
    return w_CDSA(dm, fl);
}
static LONG WINAPI w_h_CDSEA(LPCSTR dev, void *dm, HWND h, DWORD fl, LPVOID p) {
    if (from_game(__builtin_return_address(0))) {
        WLOG("[win] ChangeDisplaySettingsExA(%p, %lx) blocked\n", dm, (unsigned long)fl);
        if (!dm) w_leave_border();
        return DISP_CHANGE_SUCCESSFUL;
    }
    return w_CDSEA(dev, dm, h, fl, p);
}

// ---------- 引擎的視窗操作
// 外框尺寸 → 內容區尺寸（依目前樣式）
static void w_req_client(HWND h, int cx, int cy, int *cw, int *ch) {
    RECT fr = {0, 0, 0, 0};
    w_AWRE(&fr, (DWORD)GetWindowLongA(h, GWL_STYLE) & ~WS_MAXIMIZE, FALSE, (DWORD)GetWindowLongA(h, GWL_EXSTYLE));
    *cw = cx - (fr.right - fr.left); *ch = cy - (fr.bottom - fr.top);
}
static LONG WINAPI w_h_SWLA(HWND h, int i, LONG v) {
    if (h == g_w_main && i == GWL_STYLE && from_game(__builtin_return_address(0))) {
        WLOG("[win] engine style %08lx\n", (unsigned long)v);
        if (v & WS_POPUP) {
            if (IsZoomed(h)) { w_enter_border(); ShowWindow(h, SW_SHOWNORMAL); }
            else w_enter_border();
        } else if (g_border) w_leave_border();
        v = (LONG)w_fix_style((DWORD)v);
    }
    return w_SWLA(h, i, v);
}
static BOOL WINAPI w_h_SWP(HWND h, HWND a, int x, int y, int cx, int cy, UINT f) {
    if (h != g_w_main || !from_game(__builtin_return_address(0))) return w_SWP(h, a, x, y, cx, cy, f);
    if (g_border) {
        if (!(f & SWP_NOSIZE)) { g_eng_w = cx; g_eng_h = cy; WLOG("[win] engine size (borderless) %dx%d\n", cx, cy); }
        f &= ~(SWP_NOSIZE | SWP_NOMOVE);
        return w_SWP(h, a, g_mon.left, g_mon.top, g_mon.right - g_mon.left, g_mon.bottom - g_mon.top, f);
    }
    if (!(f & SWP_NOSIZE)) {
        int rw, rh; w_req_client(h, cx, cy, &rw, &rh);
        if (rw == g_eng_w && rh == g_eng_h && (IsZoomed(h) || w_scaled(NULL))) {
            // 引擎重新套用同一個尺寸（切換畫面時會這樣做）：保留使用者的縮放／最大化
            WLOG("[win] engine re-applies %dx%d, kept\n", rw, rh);
            return w_SWP(h, a, x, y, cx, cy, f | SWP_NOSIZE | SWP_NOMOVE);
        }
        if (IsZoomed(h)) ShowWindow(h, SW_SHOWNORMAL);
        BOOL r = w_SWP(h, a, x, y, cx, cy, f);
        w_update_eng();
        return r;
    }
    return w_SWP(h, a, x, y, cx, cy, f);
}
static BOOL WINAPI w_h_MW(HWND h, int x, int y, int cx, int cy, BOOL rp) {
    if (h != g_w_main || !from_game(__builtin_return_address(0))) return w_MW(h, x, y, cx, cy, rp);
    if (g_border) { g_eng_w = cx; g_eng_h = cy; return w_MW(h, g_mon.left, g_mon.top, g_mon.right - g_mon.left, g_mon.bottom - g_mon.top, rp); }
    int rw, rh; w_req_client(h, cx, cy, &rw, &rh);
    if (rw == g_eng_w && rh == g_eng_h && (IsZoomed(h) || w_scaled(NULL))) return TRUE;
    if (IsZoomed(h)) ShowWindow(h, SW_SHOWNORMAL);
    BOOL r = w_MW(h, x, y, cx, cy, rp); w_update_eng(); return r;
}
static BOOL WINAPI w_h_SW(HWND h, int cmd) {
    if (h == g_w_main && from_game(__builtin_return_address(0))) {
        WLOG("[win] engine ShowWindow(%d) zoomed=%d\n", cmd, IsZoomed(h));
        // 引擎切換畫面時會 ShowWindow(SW_SHOWNORMAL／SW_RESTORE)：使用者最大化中就不要讓它還原
        if (IsZoomed(h) && (cmd == SW_SHOWNORMAL || cmd == SW_RESTORE || cmd == SW_SHOW || cmd == SW_SHOWNA)) return TRUE;
    }
    return w_SW(h, cmd);
}
static BOOL WINAPI w_h_SWPL(HWND h, const WINDOWPLACEMENT *wp) {
    if (h == g_w_main && from_game(__builtin_return_address(0))) WLOG("[win] engine SetWindowPlacement show=%u\n", wp ? wp->showCmd : 0);
    return w_SWPL(h, wp);
}
static BOOL WINAPI w_h_AWR(LPRECT r, DWORD st, BOOL m) {
    if (from_game(__builtin_return_address(0))) st = w_fix_style(st);
    return w_AWR(r, st, m);
}
static BOOL WINAPI w_h_AWRE(LPRECT r, DWORD st, BOOL m, DWORD ex) {
    if (from_game(__builtin_return_address(0))) st = w_fix_style(st);
    return w_AWRE(r, st, m, ex);
}
static BOOL WINAPI w_h_GCR(HWND h, LPRECT r) {
    BOOL ok = w_GCR(h, r);
    if (ok && h == g_w_main && from_game(__builtin_return_address(0)) && w_scaled(NULL)) SetRect(r, 0, 0, g_eng_w, g_eng_h);
    return ok;
}
static BOOL WINAPI w_h_S2C(HWND h, LPPOINT p) {
    BOOL ok = w_S2C(h, p);
    if (ok && p && h == g_w_main && from_game(__builtin_return_address(0))) { int x, y; w_to_eng(p->x, p->y, &x, &y); p->x = x; p->y = y; }
    return ok;
}
static BOOL WINAPI w_h_C2S(HWND h, LPPOINT p) {
    if (p && h == g_w_main && from_game(__builtin_return_address(0))) { int x, y; w_from_eng(p->x, p->y, &x, &y); p->x = x; p->y = y; }
    return w_C2S(h, p);
}

// ---------- 視窗程序
static void w_aspect_sizing(WPARAM edge, RECT *r) {
    if (g_eng_w <= 0 || g_eng_h <= 0) return;
    RECT fr = {0, 0, 0, 0};
    w_AWRE(&fr, (DWORD)GetWindowLongA(g_w_main, GWL_STYLE), FALSE, (DWORD)GetWindowLongA(g_w_main, GWL_EXSTYLE));
    int fw = (fr.right - fr.left), fh = (fr.bottom - fr.top);
    int cw = (r->right - r->left) - fw, ch = (r->bottom - r->top) - fh;
    if (cw < 320) cw = 320;
    if (edge == WMSZ_TOP || edge == WMSZ_BOTTOM) cw = (int)((long long)ch * g_eng_w / g_eng_h);
    else ch = (int)((long long)cw * g_eng_h / g_eng_w);
    int W = cw + fw, H = ch + fh;
    switch (edge) {
    case WMSZ_LEFT: case WMSZ_TOPLEFT: case WMSZ_BOTTOMLEFT: r->left = r->right - W; break;
    default: r->right = r->left + W; break;
    }
    switch (edge) {
    case WMSZ_TOP: case WMSZ_TOPLEFT: case WMSZ_TOPRIGHT: r->top = r->bottom - H; break;
    default: r->bottom = r->top + H; break;
    }
}
static LRESULT CALLBACK w_proc(HWND h, UINT m, WPARAM wp, LPARAM lp) {
    switch (m) {
    case WM_SIZING:
        if (!g_border) { w_aspect_sizing(wp, (RECT *)lp); return TRUE; }
        break;
    case WM_SIZE:
        if (wp != SIZE_MINIMIZED && w_scaled(NULL)) {   // 引擎不需要知道（它會把視窗彈回原尺寸）
            WLOG("[win] WM_SIZE %u %ux%u kept from engine\n", (UINT)wp, LOWORD(lp), HIWORD(lp));
            InvalidateRect(h, NULL, FALSE);
            return 0;
        }
        break;
    case WM_SYSCOMMAND:
        WLOG("[win] WM_SYSCOMMAND %x\n", (UINT)(wp & 0xFFF0));
        break;
    case WM_ZH_RESTORE:
        if (!g_border && g_have_saved) {
            WLOG("[win] restore placement show=%u\n", g_saved_wp.showCmd);
            SetWindowPlacement(h, &g_saved_wp); g_have_saved = 0;
        }
        return 0;
    case WM_ERASEBKGND:
        if (w_scaled(NULL)) { RECT cr; w_GCR(h, &cr); FillRect((HDC)wp, &cr, (HBRUSH)GetStockObject(BLACK_BRUSH)); return 1; }
        break;
    case WM_MOUSEMOVE: case WM_LBUTTONDOWN: case WM_LBUTTONUP: case WM_LBUTTONDBLCLK:
    case WM_RBUTTONDOWN: case WM_RBUTTONUP: case WM_RBUTTONDBLCLK:
    case WM_MBUTTONDOWN: case WM_MBUTTONUP: case WM_MBUTTONDBLCLK:
    case WM_XBUTTONDOWN: case WM_XBUTTONUP: case WM_XBUTTONDBLCLK:
        if (w_scaled(NULL)) {
            int x, y, in = w_to_eng((short)LOWORD(lp), (short)HIWORD(lp), &x, &y);
            if (!in && (m == WM_LBUTTONDOWN || m == WM_RBUTTONDOWN || m == WM_MBUTTONDOWN || m == WM_XBUTTONDOWN ||
                        m == WM_LBUTTONDBLCLK || m == WM_RBUTTONDBLCLK || m == WM_MBUTTONDBLCLK || m == WM_XBUTTONDBLCLK))
                return 0;   // 黑邊上的點擊不起作用
            lp = MAKELPARAM(x, y);
        }
        break;
    }
    return CallWindowProcA(g_w_proc, h, m, wp, lp);
}

// 由 h_CWEA 呼叫
static DWORD win_create_style(LPCSTR cls, DWORD st) {
    if (!g_win_enable || IS_INTRESOURCE(cls) || strcmp(cls, "CoreSystem2") != 0) return st;
    return w_fix_style(st);
}
static void win_on_create(HWND h, LPCSTR cls) {
    if (!g_win_enable || !h || g_w_main || IS_INTRESOURCE(cls) || strcmp(cls, "CoreSystem2") != 0) return;
    g_w_main = h;
    w_update_eng();
    g_w_proc = (WNDPROC)w_SWLA(h, GWL_WNDPROC, (LONG)(LONG_PTR)w_proc);
    WLOG("[win] main window %p subclassed\n", h);
}
static void win_install(void) {
    if (!g_win_enable) return;
    hook("d3d9.dll", "Direct3DCreate9", (void *)w_h_D3DC9, (void **)&w_D3DC9);
    hook("user32.dll", "SetWindowPos", (void *)w_h_SWP, (void **)&w_SWP);
    hook("user32.dll", "MoveWindow", (void *)w_h_MW, (void **)&w_MW);
    hook("user32.dll", "SetWindowLongA", (void *)w_h_SWLA, (void **)&w_SWLA);
    hook("user32.dll", "AdjustWindowRect", (void *)w_h_AWR, (void **)&w_AWR);
    hook("user32.dll", "AdjustWindowRectEx", (void *)w_h_AWRE, (void **)&w_AWRE);
    hook("user32.dll", "GetClientRect", (void *)w_h_GCR, (void **)&w_GCR);
    hook("user32.dll", "ScreenToClient", (void *)w_h_S2C, (void **)&w_S2C);
    hook("user32.dll", "ClientToScreen", (void *)w_h_C2S, (void **)&w_C2S);
    hook("user32.dll", "ShowWindow", (void *)w_h_SW, (void **)&w_SW);
    hook("user32.dll", "SetWindowPlacement", (void *)w_h_SWPL, (void **)&w_SWPL);
    hook("user32.dll", "ChangeDisplaySettingsA", (void *)w_h_CDSA, (void **)&w_CDSA);
    hook("user32.dll", "ChangeDisplaySettingsExA", (void *)w_h_CDSEA, (void **)&w_CDSEA);
    if (!w_GCR) w_GCR = (wGCR_t)GetProcAddress(GetModuleHandleA("user32.dll"), "GetClientRect");
    if (!w_AWRE) w_AWRE = (wAWRE_t)GetProcAddress(GetModuleHandleA("user32.dll"), "AdjustWindowRectEx");
    if (!w_SWLA) w_SWLA = (wSWLA_t)GetProcAddress(GetModuleHandleA("user32.dll"), "SetWindowLongA");
}

