// ---------------------------------------------------------------- 視窗／繪圖行為探測（[diag] wnd=1，僅診斷用）
// 記錄：Direct3D 9 建立裝置與 Reset 的參數、Present 的呼叫（尺寸變化時）、遊戲自己呼叫的
// SetWindowPos／MoveWindow／SetWindowLongA、主視窗收到的尺寸／按鍵／系統指令訊息。
// g_diag_wnd 宣告於 zhtw_hook.c 前段
typedef void *(WINAPI *D3DC9_t)(UINT);
typedef HRESULT (WINAPI *CDev_t)(void *, UINT, int, HWND, DWORD, void *, void **);
typedef HRESULT (WINAPI *Reset_t)(void *, void *);
typedef HRESULT (WINAPI *Present_t)(void *, const RECT *, const RECT *, HWND, const RGNDATA *);
static D3DC9_t o_D3DC9; static CDev_t o_CDev; static Reset_t o_Reset; static Present_t o_Present;
typedef BOOL (WINAPI *SWP_t)(HWND, HWND, int, int, int, int, UINT);
typedef BOOL (WINAPI *MW_t)(HWND, int, int, int, int, BOOL);
typedef LONG (WINAPI *SWLA_t)(HWND, int, LONG);
static SWP_t o_SWP; static MW_t o_MW; static SWLA_t o_SWLA;
static HWND g_main; static WNDPROC g_main_proc;

// D3DPRESENT_PARAMETERS（x86）前段欄位
typedef struct { UINT bbw, bbh, fmt, bbcount, mstype, msq, swap; HWND wnd; BOOL windowed, autods; UINT dsfmt, flags, refresh, interval; } PP;
static void log_pp(const char *tag, const PP *p) {
    logf("[wnd] %s bb=%ux%u fmt=%u cnt=%u swap=%u hwnd=%p windowed=%d flags=%x refresh=%u interval=%x\n",
         tag, p->bbw, p->bbh, p->fmt, p->bbcount, p->swap, p->wnd, p->windowed, p->flags, p->refresh, p->interval);
}
static HRESULT WINAPI h_Present(void *dev, const RECT *s, const RECT *d, HWND w, const RGNDATA *r) {
    static RECT last; RECT cr = {0}; if (g_main) GetClientRect(g_main, &cr);
    if (memcmp(&cr, &last, sizeof cr)) {
        last = cr;
        logf("[wnd] Present client=%ldx%ld src=%s dst=%s hwnd=%p\n", cr.right, cr.bottom, s ? "set" : "null", d ? "set" : "null", w);
    }
    return o_Present(dev, s, d, w, r);
}
static HRESULT WINAPI h_Reset(void *dev, void *pp) {
    log_pp("Reset", (PP *)pp);
    HRESULT r = o_Reset(dev, pp); logf("[wnd] Reset -> %08lx\n", (unsigned long)r); return r;
}
static HRESULT WINAPI h_CDev(void *d3d, UINT ad, int type, HWND focus, DWORD beh, void *pp, void **out) {
    log_pp("CreateDevice", (PP *)pp);
    HRESULT r = o_CDev(d3d, ad, type, focus, beh, pp, out);
    logf("[wnd] CreateDevice -> %08lx focus=%p beh=%lx\n", (unsigned long)r, focus, (unsigned long)beh);
    if (r == 0 && out && *out && !o_Present) {
        void **vt = *(void ***)*out;
        MH_CreateHook(vt[16], (void *)h_Reset, (void **)&o_Reset); MH_EnableHook(vt[16]);
        MH_CreateHook(vt[17], (void *)h_Present, (void **)&o_Present); MH_EnableHook(vt[17]);
    }
    return r;
}
static void *WINAPI h_D3DC9(UINT v) {
    void *d = o_D3DC9(v);
    logf("[wnd] Direct3DCreate9(%u) -> %p\n", v, d);
    if (d && !o_CDev) { void **vt = *(void ***)d; MH_CreateHook(vt[16], (void *)h_CDev, (void **)&o_CDev); MH_EnableHook(vt[16]); }
    return d;
}
static BOOL WINAPI h_SWP(HWND h, HWND a, int x, int y, int cx, int cy, UINT f) {
    if (h == g_main && from_exe(__builtin_return_address(0))) logf("[wnd] SetWindowPos %d,%d %dx%d flags=%x\n", x, y, cx, cy, f);
    return o_SWP(h, a, x, y, cx, cy, f);
}
static BOOL WINAPI h_MW(HWND h, int x, int y, int cx, int cy, BOOL rp) {
    if (h == g_main && from_exe(__builtin_return_address(0))) logf("[wnd] MoveWindow %d,%d %dx%d\n", x, y, cx, cy);
    return o_MW(h, x, y, cx, cy, rp);
}
static LONG WINAPI h_SWLA(HWND h, int i, LONG v) {
    if (h == g_main && from_exe(__builtin_return_address(0)) && (i == GWL_STYLE || i == GWL_EXSTYLE)) logf("[wnd] SetWindowLongA %s=%08lx\n", i == GWL_STYLE ? "STYLE" : "EXSTYLE", (unsigned long)v);
    return o_SWLA(h, i, v);
}
static LRESULT CALLBACK probe_proc(HWND h, UINT m, WPARAM w, LPARAM l) {
    switch (m) {
    case WM_SIZE: logf("[wnd] WM_SIZE type=%u %ux%u\n", (UINT)w, LOWORD(l), HIWORD(l)); break;
    case WM_GETMINMAXINFO: { LRESULT r = CallWindowProcA(g_main_proc, h, m, w, l); MINMAXINFO *mm = (MINMAXINFO *)l;
        logf("[wnd] WM_GETMINMAXINFO -> max=%ldx%ld track=%ldx%ld..%ldx%ld\n", mm->ptMaxSize.x, mm->ptMaxSize.y, mm->ptMinTrackSize.x, mm->ptMinTrackSize.y, mm->ptMaxTrackSize.x, mm->ptMaxTrackSize.y); return r; }
    case WM_SYSKEYDOWN: logf("[wnd] WM_SYSKEYDOWN vk=%u\n", (UINT)w); break;
    case WM_SYSCOMMAND: logf("[wnd] WM_SYSCOMMAND %x\n", (UINT)(w & 0xFFF0)); break;
    case WM_ENTERSIZEMOVE: logf("[wnd] WM_ENTERSIZEMOVE\n"); break;
    case WM_EXITSIZEMOVE: logf("[wnd] WM_EXITSIZEMOVE\n"); break;
    case WM_DISPLAYCHANGE: logf("[wnd] WM_DISPLAYCHANGE %ux%u\n", LOWORD(l), HIWORD(l)); break;
    case WM_MOUSEMOVE: { static int n = 0; if (n++ < 5) logf("[wnd] WM_MOUSEMOVE %d,%d\n", (short)LOWORD(l), (short)HIWORD(l)); } break;
    }
    return CallWindowProcA(g_main_proc, h, m, w, l);
}
// 由 h_CWEA 呼叫：主視窗建立後掛上探測用的視窗程序
static void wnd_probe_on_create(HWND h, LPCSTR cls, DWORD style, DWORD ex) {
    if (!g_diag_wnd || !h || g_main) return;
    if (IS_INTRESOURCE(cls) || strcmp(cls, "CoreSystem2") != 0) return;
    g_main = h;
    logf("[wnd] main window %p style=%08lx ex=%08lx\n", h, (unsigned long)style, (unsigned long)ex);
    g_main_proc = (WNDPROC)SetWindowLongA(h, GWL_WNDPROC, (LONG)(LONG_PTR)probe_proc);
}
static void wnd_probe_install(void) {
    if (!g_diag_wnd) return;
    hook("d3d9.dll", "Direct3DCreate9", (void *)h_D3DC9, (void **)&o_D3DC9);
    hook("user32.dll", "SetWindowPos", (void *)h_SWP, (void **)&o_SWP);
    hook("user32.dll", "MoveWindow", (void *)h_MW, (void **)&o_MW);
    hook("user32.dll", "SetWindowLongA", (void *)h_SWLA, (void **)&o_SWLA);
}

