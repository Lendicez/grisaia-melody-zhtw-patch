// ---------------------------------------------------------------- 系統環境設定對話框（cs2conf.dll）
// cs2conf 以 A 版 API 建立屬性表與清單：屬性表標題、分頁名稱、ListView 欄位與項目都會被 comctl32
// 用系統代碼頁（CP950）解讀而變成亂碼。這裡把這些字串以 CP932（含借位碼）轉成 Unicode 再送 W 版。
#include <commctrl.h>
#include <prsht.h>

// ---- ListView／TabCtrl 的 A 版訊息 → W 版
static int dlg_conv_msg(HWND h, UINT msg, WPARAM wp, LPARAM lp, LRESULT *res) {
    UINT wmsg = 0; int off = 0, need_mask = 0; UINT maskbit = 0, size = 0;
    switch (msg) {
    case LVM_INSERTCOLUMNA: wmsg = LVM_INSERTCOLUMNW; off = 12; maskbit = LVCF_TEXT; need_mask = 1; size = sizeof(LVCOLUMNA); break;
    case LVM_SETCOLUMNA:    wmsg = LVM_SETCOLUMNW;    off = 12; maskbit = LVCF_TEXT; need_mask = 1; size = sizeof(LVCOLUMNA); break;
    case LVM_INSERTITEMA:   wmsg = LVM_INSERTITEMW;   off = 20; maskbit = LVIF_TEXT; need_mask = 1; size = sizeof(LVITEMA); break;
    case LVM_SETITEMA:      wmsg = LVM_SETITEMW;      off = 20; maskbit = LVIF_TEXT; need_mask = 1; size = sizeof(LVITEMA); break;
    case LVM_SETITEMTEXTA:  wmsg = LVM_SETITEMTEXTW;  off = 20; size = sizeof(LVITEMA); break;
    case TCM_INSERTITEMA:   wmsg = TCM_INSERTITEMW;   off = 12; maskbit = TCIF_TEXT; need_mask = 1; size = sizeof(TCITEMA); break;
    case TCM_SETITEMA:      wmsg = TCM_SETITEMW;      off = 12; maskbit = TCIF_TEXT; need_mask = 1; size = sizeof(TCITEMA); break;
    default: return 0;
    }
    if (!lp) return 0;
    if (need_mask && !(*(UINT *)lp & maskbit)) return 0;
    LPCSTR t = *(LPCSTR *)((BYTE *)lp + off);
    if (!t || t == LPSTR_TEXTCALLBACKA || IS_INTRESOURCE(t) || !has_high(t)) return 0;
    BYTE copy[96]; if (size > sizeof copy) return 0;
    memcpy(copy, (void *)lp, size);
    WCHAR *w = dup932(t); if (!w) return 0;
    *(WCHAR **)(copy + off) = w;
    *res = SendMessageW(h, wmsg, wp, (LPARAM)copy);
    freew(w);
    return 1;
}

typedef LRESULT (WINAPI *SDIMA_t)(HWND, int, UINT, WPARAM, LPARAM);
static SDIMA_t o_SDIMA;
static void dlg_check_conf(void);
static LRESULT WINAPI h_SDIMA(HWND d, int id, UINT msg, WPARAM wp, LPARAM lp) {
    if (from_exe(__builtin_return_address(0))) {
        dlg_check_conf();
        LRESULT r; HWND c = GetDlgItem(d, id);
        if (c && dlg_conv_msg(c, msg, wp, lp, &r)) return r;
        if (c && (msg == WM_SETTEXT || msg == CB_ADDSTRING || msg == LB_ADDSTRING || msg == CB_INSERTSTRING || msg == LB_INSERTSTRING) && has_high((LPCSTR)lp)) {
            WCHAR *w = dup932((LPCSTR)lp); r = SendMessageW(c, msg, wp, (LPARAM)w); freew(w); return r;
        }
    }
    return o_SDIMA(d, id, msg, wp, lp);
}

// ---- 屬性表：記下各分頁標題與表頭標題，表單建立後以 W 版改寫
typedef HPROPSHEETPAGE (WINAPI *CPSPA_t)(LPCPROPSHEETPAGEA);
typedef INT_PTR (WINAPI *PSA_t)(LPCPROPSHEETHEADERA);
static CPSPA_t o_CPSPA; static PSA_t o_PSA; static PSA_t o_PSA2; static CPSPA_t o_CPSPA2;
#define DLG_MAXP 32
static struct { HPROPSHEETPAGE h; char title[128]; } g_pages[DLG_MAXP]; static int g_npages;
static char g_ps_caption[256]; static PFNPROPSHEETCALLBACK g_ps_orig_cb; static DWORD g_ps_flags;
static HPROPSHEETPAGE g_ps_order[DLG_MAXP]; static int g_ps_n;

static HPROPSHEETPAGE cpspa_common(CPSPA_t orig, LPCPROPSHEETPAGEA p) {
    HPROPSHEETPAGE h = orig(p);
    if (h && p && (p->dwFlags & PSP_USETITLE) && p->pszTitle && !IS_INTRESOURCE(p->pszTitle) && g_npages < DLG_MAXP) {
        g_pages[g_npages].h = h;
        lstrcpynA(g_pages[g_npages].title, p->pszTitle, sizeof g_pages[0].title);
        g_npages++;
        logf("[dlg] page %p title set\n", h);
    }
    return h;
}
static HPROPSHEETPAGE WINAPI h_CPSPA(LPCPROPSHEETPAGEA p) { return cpspa_common(o_CPSPA, p); }
static const char *page_title(HPROPSHEETPAGE h) {
    for (int i = 0; i < g_npages; i++) if (g_pages[i].h == h) return g_pages[i].title;
    return NULL;
}
static VOID CALLBACK ps_fix_timer(HWND hw, UINT m, UINT_PTR id, DWORD t) {
    KillTimer(hw, id);
    if (g_ps_caption[0] && has_high(g_ps_caption) && !(g_ps_flags & PSH_PROPTITLE)) {
        WCHAR *w = dup932(g_ps_caption); if (w) { SetWindowTextW(hw, w); freew(w); }
    }
    HWND tab = (HWND)SendMessageW(hw, PSM_GETTABCONTROL, 0, 0);
    if (!tab) return;
    int n = (int)SendMessageW(tab, TCM_GETITEMCOUNT, 0, 0);
    for (int i = 0; i < n && i < g_ps_n; i++) {
        const char *t = page_title(g_ps_order[i]);
        if (!t || !has_high(t)) continue;
        WCHAR *w = dup932(t); if (!w) continue;
        TCITEMW it; memset(&it, 0, sizeof it); it.mask = TCIF_TEXT; it.pszText = w;
        SendMessageW(tab, TCM_SETITEMW, i, (LPARAM)&it);
        freew(w);
    }
    logf("[dlg] property sheet fixed: %d tabs\n", n);
}
static int CALLBACK ps_cb(HWND hw, UINT msg, LPARAM lp) {
    int r = g_ps_orig_cb ? g_ps_orig_cb(hw, msg, lp) : 0;
    if (msg == PSCB_INITIALIZED && hw) SetTimer(hw, 0x5A17, 1, ps_fix_timer);
    return r;
}
static INT_PTR psa_common(PSA_t orig, LPCPROPSHEETHEADERA ph) {
    if (!ph || ph->dwSize > 128 || (ph->dwFlags & PSH_PROPSHEETPAGE)) return orig(ph);
    BYTE buf[128]; memcpy(buf, ph, ph->dwSize);
    PROPSHEETHEADERA *c = (PROPSHEETHEADERA *)buf;
    g_ps_caption[0] = 0;
    if (c->pszCaption && !IS_INTRESOURCE(c->pszCaption)) lstrcpynA(g_ps_caption, c->pszCaption, sizeof g_ps_caption);
    g_ps_flags = c->dwFlags;
    g_ps_n = c->nPages < DLG_MAXP ? (int)c->nPages : DLG_MAXP;
    for (int i = 0; i < g_ps_n; i++) g_ps_order[i] = c->phpage[i];
    g_ps_orig_cb = (c->dwFlags & PSH_USECALLBACK) ? c->pfnCallback : NULL;
    c->dwFlags |= PSH_USECALLBACK; c->pfnCallback = ps_cb;
    logf("[dlg] PropertySheetA pages=%d flags=%lx\n", g_ps_n, (unsigned long)g_ps_flags);
    return orig(c);
}
static INT_PTR WINAPI h_PSA(LPCPROPSHEETHEADERA ph) { return psa_common(o_PSA, ph); }
static INT_PTR WINAPI h_PSA2(LPCPROPSHEETHEADERA ph) { return psa_common(o_PSA2, ph); }
static HPROPSHEETPAGE WINAPI h_CPSPA2(LPCPROPSHEETPAGEA p) { return cpspa_common(o_CPSPA2, p); }

// ---- 屬性表由遊戲本體（或 cs2conf）呼叫 comctl32!PropertySheetA；可能載入兩份 comctl32（v5／v6），
//      各自掛一次（每份用不同的轉接函式，才能呼叫到各自的原函式）。在主視窗建立與 LoadLibrary 之後檢查。
static HMODULE g_cc_hooked[2];
static volatile LONG g_cc_busy = 0;
static void dlg_check_conf(void) {
    if (InterlockedExchange(&g_cc_busy, 1)) return;
    typedef BOOL (WINAPI *EPM)(HANDLE, HMODULE *, DWORD, LPDWORD);
    typedef DWORD (WINAPI *GMBN)(HANDLE, HMODULE, LPSTR, DWORD);
    static EPM epm; static GMBN gmbn;
    if (!epm) { epm = (EPM)GetProcAddress(GetModuleHandleA("kernel32.dll"), "K32EnumProcessModules"); gmbn = (GMBN)GetProcAddress(GetModuleHandleA("kernel32.dll"), "K32GetModuleBaseNameA"); }
    HMODULE mods[512]; DWORD need = 0;
    if (epm && gmbn && epm(GetCurrentProcess(), mods, sizeof mods, &need)) {
        for (DWORD i = 0; i < need / sizeof(HMODULE) && i < 512; i++) {
            if (mods[i] == g_cc_hooked[0] || mods[i] == g_cc_hooked[1]) continue;
            char nm[64]; if (!gmbn(GetCurrentProcess(), mods[i], nm, sizeof nm) || lstrcmpiA(nm, "comctl32.dll") != 0) continue;
            void *pa = (void *)GetProcAddress(mods[i], "PropertySheetA"), *ca = (void *)GetProcAddress(mods[i], "CreatePropertySheetPageA");
            int slot = !g_cc_hooked[0] ? 0 : (!g_cc_hooked[1] ? 1 : -1);
            if (slot < 0 || !pa || !ca) continue;
            g_cc_hooked[slot] = mods[i];
            if (slot == 0) { MH_CreateHook(pa, (void *)h_PSA, (void **)&o_PSA); MH_EnableHook(pa); MH_CreateHook(ca, (void *)h_CPSPA, (void **)&o_CPSPA); MH_EnableHook(ca); }
            else { MH_CreateHook(pa, (void *)h_PSA2, (void **)&o_PSA2); MH_EnableHook(pa); MH_CreateHook(ca, (void *)h_CPSPA2, (void **)&o_CPSPA2); MH_EnableHook(ca); }
            logf("[dlg] comctl32 %p hooked (slot %d)\n", mods[i], slot);
        }
    }
    InterlockedExchange(&g_cc_busy, 0);
}
typedef HMODULE (WINAPI *LLA_t)(LPCSTR); typedef HMODULE (WINAPI *LLEA_t)(LPCSTR, HANDLE, DWORD);
typedef HMODULE (WINAPI *LLW_t)(LPCWSTR); typedef HMODULE (WINAPI *LLEW_t)(LPCWSTR, HANDLE, DWORD);
static LLA_t o_LLA; static LLEA_t o_LLEA; static LLW_t o_LLW; static LLEW_t o_LLEW;
static HMODULE WINAPI h_LLA(LPCSTR n) { HMODULE m = o_LLA(n); if (n && strstr(n, "cs2")) logf("[dlg] LoadLibraryA %s -> %p\n", n, m); dlg_check_conf(); return m; }
static HMODULE WINAPI h_LLEA(LPCSTR n, HANDLE f, DWORD fl) { HMODULE m = o_LLEA(n, f, fl); if (n && strstr(n, "cs2")) logf("[dlg] LoadLibraryExA %s -> %p\n", n, m); dlg_check_conf(); return m; }
static HMODULE WINAPI h_LLW(LPCWSTR n) { HMODULE m = o_LLW(n); dlg_check_conf(); return m; }
static HMODULE WINAPI h_LLEW(LPCWSTR n, HANDLE f, DWORD fl) { HMODULE m = o_LLEW(n, f, fl); dlg_check_conf(); return m; }

static void dlg_install(void) {
    hook("user32.dll", "SendDlgItemMessageA", (void *)h_SDIMA, (void **)&o_SDIMA);
    hook("kernel32.dll", "LoadLibraryA", (void *)h_LLA, (void **)&o_LLA);
    hook("kernel32.dll", "LoadLibraryExA", (void *)h_LLEA, (void **)&o_LLEA);
    hook("kernel32.dll", "LoadLibraryW", (void *)h_LLW, (void **)&o_LLW);
    hook("kernel32.dll", "LoadLibraryExW", (void *)h_LLEW, (void **)&o_LLEW);
    dlg_check_conf();
}

