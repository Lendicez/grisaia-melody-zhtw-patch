// zhtw_hook.c — version.dll proxy for CatSystem2 (The Melody of Grisaia, Steam) 繁體中文顯示
//
// 作用（只對主程式模組呼叫生效）：
//   * SJIS 隧道：劇本仍是 CP932 位元組；不在 CP932 的繁體字以「隧道碼」（借用譯文沒用到的 CP932 雙位元碼）
//     存放，顯示時由 zhtw_map.bin 轉回真正的 Unicode。
//   * MultiByteToWideChar(932/ACP) → CP932 解碼＋隧道對照
//   * GetGlyphOutlineA / GetTextExtentPoint32A → 轉成 W 版呼叫
//   * CreateFontIndirectA → 依 zhtw.ini 換字型（預設 Microsoft JhengHei）、字集改 DEFAULT_CHARSET
//   * 可選記錄（zhtw.ini [log] enable=1）→ zhtw_hook.log，用於診斷引擎呼叫哪些 API
// version.dll 原有匯出全部轉呼叫系統 System32\version.dll。
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include "MinHook.h"

// ---------------------------------------------------------------- config / log
static HMODULE g_self, g_exe;
static DWORD_PTR g_exe_lo, g_exe_hi;
static wchar_t g_dir[MAX_PATH];
static int g_log_enable = 0, g_log_max = 4000, g_log_count = 0;
static int g_remap_acp = 1;          // 主程式以 CP_ACP 呼叫時也視為 932
static int g_font_override = 1;
static int g_charset_override = 1;
static int g_diag_exit = 0, g_fast_exit = 0;   // [diag] 結束流程診斷／快速結束
static int g_diag_wnd = 0;                    // [diag] wnd=1 視窗／繪圖行為探測
static int g_win_enable = 0;                  // [window] enable=1 視窗化強化（等比縮放／最大化／無邊框全螢幕）
static int g_fs_enable = 1;                   // [fs] 非 ASCII 路徑改走 W 版 API（存檔資料夾）
static int g_font_scale = 100;       // 字高百分比
static char g_font_face[LF_FACESIZE] = "Microsoft JhengHei";
// 正黑體的「…」「─」等為窄字，引擎以全形格排列會斷開 → 這些符號改用全形字型（依序找第一個存在的）
static wchar_t g_punct_chars[64] = L"\x2026\x22EF\x2500\x2015\x2014\x2025\x2501";
static wchar_t g_punct_faces[256] = L"MingLiU;PMingLiU;Yu Gothic;MS Gothic";
static wchar_t g_punct_face[LF_FACESIZE];   // 實際使用者（空字串＝不用）
static CRITICAL_SECTION g_cs;
static FILE *g_log;
static int g_map_count = 0;
static unsigned short g_map[65536];  // sjis code -> unicode (0 = none)

static void logf(const char *fmt, ...) {
    if (!g_log_enable || !g_log) return;
    EnterCriticalSection(&g_cs);
    if (g_log_count < g_log_max) {
        va_list ap; va_start(ap, fmt); vfprintf(g_log, fmt, ap); va_end(ap);
        fflush(g_log); g_log_count++;
    }
    LeaveCriticalSection(&g_cs);
}

static void loghex(const char *tag, const void *p, int n) {
    if (!g_log_enable || !g_log || !p) return;
    char buf[400]; int k = 0; const unsigned char *b = (const unsigned char *)p;
    if (n < 0) { n = 0; while (b[n] && n < 96) n++; }
    if (n > 96) n = 96;
    for (int i = 0; i < n && k < 380; i++) k += sprintf(buf + k, "%02X", b[i]);
    buf[k] = 0;
    logf("  %s[%d] %s\n", tag, n, buf);
}

static DWORD_PTR g_conf_lo, g_conf_hi;
static int in_module(DWORD_PTR r, const char *name, DWORD_PTR *lo, DWORD_PTR *hi) {
    if (!*lo) {
        HMODULE m = GetModuleHandleA(name);
        if (!m) return 0;
        IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)((BYTE *)m + ((IMAGE_DOS_HEADER *)m)->e_lfanew);
        *lo = (DWORD_PTR)m; *hi = *lo + nt->OptionalHeader.SizeOfImage;
    }
    return r >= *lo && r < *hi;
}
static int from_exe(void *ret) {
    DWORD_PTR r = (DWORD_PTR)ret;
    return (r >= g_exe_lo && r < g_exe_hi) || in_module(r, "cs2conf.dll", &g_conf_lo, &g_conf_hi);
}

static void load_config(void) {
    wchar_t ini[MAX_PATH];
    swprintf(ini, MAX_PATH, L"%ls\\zhtw.ini", g_dir);
    g_log_enable = GetPrivateProfileIntW(L"log", L"enable", 0, ini);
    g_log_max = GetPrivateProfileIntW(L"log", L"max", 4000, ini);
    g_remap_acp = GetPrivateProfileIntW(L"text", L"remap_acp", 1, ini);
    g_font_override = GetPrivateProfileIntW(L"font", L"override", 1, ini);
    g_charset_override = GetPrivateProfileIntW(L"font", L"charset_override", 1, ini);
    g_font_scale = GetPrivateProfileIntW(L"font", L"scale", 100, ini);
    g_diag_exit = GetPrivateProfileIntW(L"diag", L"exit", 0, ini);
    g_fast_exit = GetPrivateProfileIntW(L"diag", L"fast_exit", 0, ini);
    g_fs_enable = GetPrivateProfileIntW(L"fs", L"enable", 1, ini);
    g_diag_wnd = GetPrivateProfileIntW(L"diag", L"wnd", 0, ini);
    g_win_enable = GetPrivateProfileIntW(L"window", L"enable", 0, ini);
    wchar_t face[LF_FACESIZE];
    if (GetPrivateProfileStringW(L"font", L"face", L"", face, LF_FACESIZE, ini) > 0)
        WideCharToMultiByte(CP_ACP, 0, face, -1, g_font_face, LF_FACESIZE, NULL, NULL);
    GetPrivateProfileStringW(L"font", L"punct_faces", g_punct_faces, g_punct_faces, 256, ini);
    {
        wchar_t pc[64];
        if (GetPrivateProfileStringW(L"font", L"punct_chars", L"", pc, 64, ini) > 0) wcscpy(g_punct_chars, pc);
    }
    if (g_log_enable) {
        wchar_t lp[MAX_PATH];
        swprintf(lp, MAX_PATH, L"%ls\\zhtw_hook.log", g_dir);
        g_log = _wfopen(lp, L"w");
    }
    // map file: "ZHMP" uint32 count, count x (uint16 sjis, uint16 unicode)
    wchar_t mp[MAX_PATH];
    swprintf(mp, MAX_PATH, L"%ls\\zhtw_map.bin", g_dir);
    FILE *f = _wfopen(mp, L"rb");
    if (f) {
        char magic[4]; unsigned int n = 0;
        if (fread(magic, 1, 4, f) == 4 && memcmp(magic, "ZHMP", 4) == 0 && fread(&n, 4, 1, f) == 1) {
            for (unsigned int i = 0; i < n; i++) {
                unsigned short pr[2];
                if (fread(pr, 2, 2, f) != 2) break;
                g_map[pr[0]] = pr[1]; g_map_count++;
            }
        }
        fclose(f);
    }
}

static int is_lead(unsigned char c) { return (c >= 0x81 && c <= 0x9F) || (c >= 0xE0 && c <= 0xFC); }

// ---------------------------------------------------------------- originals
typedef int (WINAPI *MBTWC_t)(UINT, DWORD, LPCCH, int, LPWSTR, int);
typedef int (WINAPI *WCTMB_t)(UINT, DWORD, LPCWCH, int, LPSTR, int, LPCCH, LPBOOL);
typedef DWORD (WINAPI *GGOA_t)(HDC, UINT, UINT, LPGLYPHMETRICS, DWORD, LPVOID, const MAT2 *);
typedef DWORD (WINAPI *GGOW_t)(HDC, UINT, UINT, LPGLYPHMETRICS, DWORD, LPVOID, const MAT2 *);
typedef BOOL (WINAPI *GTEPA_t)(HDC, LPCSTR, int, LPSIZE);
typedef BOOL (WINAPI *GTEPW_t)(HDC, LPCWSTR, int, LPSIZE);
typedef HFONT (WINAPI *CFIA_t)(const LOGFONTA *);
typedef BOOL (WINAPI *GTMA_t)(HDC, LPTEXTMETRICA);
static MBTWC_t o_MBTWC; static WCTMB_t o_WCTMB; static GGOA_t o_GGOA; static GGOW_t o_GGOW;
static GTEPA_t o_GTEPA; static GTEPW_t o_GTEPW; static CFIA_t o_CFIA; static GTMA_t o_GTMA;

// decode one SJIS code (lead<<8|trail or single byte) to unicode
static WCHAR sjis_to_uni(UINT code) {
    if (code > 0xFF && g_map[code & 0xFFFF]) return g_map[code & 0xFFFF];
    char b[2]; int n;
    if (code > 0xFF) { b[0] = (char)(code >> 8); b[1] = (char)code; n = 2; } else { b[0] = (char)code; n = 1; }
    WCHAR w = 0;
    if (o_MBTWC(932, 0, b, n, &w, 1) != 1) w = L'?';
    return w;
}

// CP932 decode with tunnel map; semantics of MultiByteToWideChar
static int decode932(DWORD flags, LPCCH src, int srclen, LPWSTR dst, int dstlen) {
    int n = o_MBTWC(932, flags, src, srclen, dst, dstlen);
    if (n <= 0 || !dst || dstlen == 0 || g_map_count == 0) return n;
    // walk source and output in parallel (CP932: each char -> exactly one UTF-16 unit)
    const unsigned char *s = (const unsigned char *)src;
    int len = srclen < 0 ? (int)strlen(src) + 1 : srclen;
    int i = 0, o = 0;
    while (i < len && o < n) {
        if (is_lead(s[i]) && i + 1 < len) {
            unsigned short c = (unsigned short)((s[i] << 8) | s[i + 1]);
            if (g_map[c]) dst[o] = g_map[c];
            i += 2;
        } else i += 1;
        o++;
    }
    return n;
}

static int WINAPI h_MBTWC(UINT cp, DWORD flags, LPCCH src, int srclen, LPWSTR dst, int dstlen) {
    void *ret = __builtin_return_address(0);
    if (!from_exe(ret)) return o_MBTWC(cp, flags, src, srclen, dst, dstlen);
    int high = 0;
    if (src) { int len = srclen < 0 ? (int)strlen(src) : srclen; for (int i = 0; i < len; i++) if ((unsigned char)src[i] >= 0x80) { high = 1; break; } }
    if (high) { logf("MBTWC cp=%u flags=%lx len=%d ret=%p\n", cp, (unsigned long)flags, srclen, ret); loghex("src", src, srclen); }
    if (cp == 932 || (g_remap_acp && (cp == CP_ACP || cp == CP_THREAD_ACP)))
        return decode932(flags, src, srclen, dst, dstlen);
    return o_MBTWC(cp, flags, src, srclen, dst, dstlen);
}

static int WINAPI h_WCTMB(UINT cp, DWORD flags, LPCWCH src, int srclen, LPSTR dst, int dstlen, LPCCH def, LPBOOL used) {
    void *ret = __builtin_return_address(0);
    int r = o_WCTMB(cp, flags, src, srclen, dst, dstlen, def, used);
    if (from_exe(ret) && src) {
        int high = 0; int len = srclen < 0 ? (int)wcslen(src) : srclen;
        for (int i = 0; i < len; i++) if (src[i] >= 0x80) { high = 1; break; }
        if (high) { logf("WCTMB cp=%u len=%d r=%d ret=%p\n", cp, srclen, r, ret); loghex("wsrc", src, len * 2 > 96 ? 96 : len * 2); }
    }
    return r;
}

static int CALLBACK font_exists_cb(const LOGFONTW *lf, const TEXTMETRICW *tm, DWORD t, LPARAM p) { *(int *)p = 1; return 0; }
static void pick_punct_face(void) {
    HDC dc = GetDC(NULL); wchar_t list[256]; wcscpy(list, g_punct_faces);
    wchar_t *ctx = NULL;
    for (wchar_t *tok = wcstok(list, L";", &ctx); tok; tok = wcstok(NULL, L";", &ctx)) {
        while (*tok == L' ') tok++;
        LOGFONTW lf; memset(&lf, 0, sizeof lf); lf.lfCharSet = DEFAULT_CHARSET; wcsncpy(lf.lfFaceName, tok, LF_FACESIZE - 1);
        int found = 0; EnumFontFamiliesExW(dc, &lf, (FONTENUMPROCW)font_exists_cb, (LPARAM)&found, 0);
        if (found) { wcsncpy(g_punct_face, tok, LF_FACESIZE - 1); break; }
    }
    ReleaseDC(NULL, dc);
}
typedef struct { LONG h; LONG w; LONG weight; HFONT f; } AltFont;
static AltFont g_alt[16]; static int g_alt_n = 0;
static HFONT alt_font_for(HDC hdc) {
    HFONT cur = (HFONT)GetCurrentObject(hdc, OBJ_FONT); LOGFONTW lf;
    if (!cur || !GetObjectW(cur, sizeof lf, &lf)) return NULL;
    for (int i = 0; i < g_alt_n; i++) if (g_alt[i].h == lf.lfHeight && g_alt[i].w == lf.lfWidth && g_alt[i].weight == lf.lfWeight) return g_alt[i].f;
    wcsncpy(lf.lfFaceName, g_punct_face, LF_FACESIZE - 1); lf.lfCharSet = DEFAULT_CHARSET;
    HFONT f = CreateFontIndirectW(&lf);
    if (f && g_alt_n < 16) { g_alt[g_alt_n].h = lf.lfHeight; g_alt[g_alt_n].w = lf.lfWidth; g_alt[g_alt_n].weight = lf.lfWeight; g_alt[g_alt_n].f = f; g_alt_n++; }
    return f;
}
static int g_punct_picked = 0;
static int is_punct(WCHAR w) {
    if (!w || !wcschr(g_punct_chars, w)) return 0;
    if (!g_punct_picked) { g_punct_picked = 1; pick_punct_face(); logf("punct face='%ls'\n", g_punct_face); }   // 延後到第一次繪字（避免在 DllMain 呼叫 GDI）
    return g_punct_face[0] != 0;
}

static DWORD WINAPI h_GGOA(HDC hdc, UINT ch, UINT fmt, LPGLYPHMETRICS gm, DWORD cb, LPVOID buf, const MAT2 *m) {
    void *ret = __builtin_return_address(0);
    if (!from_exe(ret)) return o_GGOA(hdc, ch, fmt, gm, cb, buf, m);
    WCHAR w = sjis_to_uni(ch);
    static int once = 0; if (once < 40 && ch > 0x7F) { once++; logf("GGOA ch=%04X -> U+%04X fmt=%u ret=%p\n", ch, w, fmt, ret); }
    if (is_punct(w)) {
        HFONT af = alt_font_for(hdc);
        if (af) {
            HGDIOBJ old = SelectObject(hdc, af);
            DWORD r = o_GGOW(hdc, w, fmt, gm, cb, buf, m);
            SelectObject(hdc, old);
            return r;
        }
    }
    return o_GGOW(hdc, w, fmt, gm, cb, buf, m);
}

static DWORD WINAPI h_GGOW(HDC hdc, UINT ch, UINT fmt, LPGLYPHMETRICS gm, DWORD cb, LPVOID buf, const MAT2 *m) {
    void *ret = __builtin_return_address(0);
    if (from_exe(ret)) {
        static int once = 0; if (once < 40 && ch > 0x7F) { once++; logf("GGOW ch=U+%04X fmt=%u ret=%p\n", ch, fmt, ret); }
    }
    return o_GGOW(hdc, ch, fmt, gm, cb, buf, m);
}

static BOOL WINAPI h_GTEPA(HDC hdc, LPCSTR s, int c, LPSIZE sz) {
    void *ret = __builtin_return_address(0);
    if (!from_exe(ret) || !s || c <= 0) return o_GTEPA(hdc, s, c, sz);
    WCHAR wb[512]; WCHAR *w = wb;
    if (c > 500) w = (WCHAR *)HeapAlloc(GetProcessHeap(), 0, (c + 1) * sizeof(WCHAR));
    int n = decode932(0, s, c, w, c + 1);
    static int once = 0; if (once < 40) { once++; logf("GTEPA c=%d ret=%p\n", c, ret); loghex("s", s, c); }
    BOOL r = o_GTEPW(hdc, w, n > 0 ? n : 0, sz);
    if (w != wb) HeapFree(GetProcessHeap(), 0, w);
    return r;
}

static HFONT WINAPI h_CFIA(const LOGFONTA *lf) {
    void *ret = __builtin_return_address(0);
    if (!from_exe(ret) || !lf) return o_CFIA(lf);
    LOGFONTA x = *lf;
    logf("CFIA face='%s' h=%ld w=%ld weight=%ld charset=%u quality=%u ret=%p\n", lf->lfFaceName, lf->lfHeight, lf->lfWidth, lf->lfWeight, lf->lfCharSet, lf->lfQuality, ret);
    if (g_font_override && g_font_face[0]) { strncpy(x.lfFaceName, g_font_face, LF_FACESIZE - 1); x.lfFaceName[LF_FACESIZE - 1] = 0; }
    if (g_charset_override) x.lfCharSet = DEFAULT_CHARSET;
    if (g_font_scale != 100) { x.lfHeight = x.lfHeight * g_font_scale / 100; x.lfWidth = x.lfWidth * g_font_scale / 100; }
    return o_CFIA(&x);
}

static BOOL WINAPI h_GTMA(HDC hdc, LPTEXTMETRICA tm) {
    BOOL r = o_GTMA(hdc, tm);
    void *ret = __builtin_return_address(0);
    if (r && from_exe(ret) && tm) {
        static int once = 0; if (once < 10) { once++; logf("GTMA h=%ld asc=%ld ave=%ld max=%ld charset=%u ret=%p\n", tm->tmHeight, tm->tmAscent, tm->tmAveCharWidth, tm->tmMaxCharWidth, tm->tmCharSet, ret); }
    }
    return r;
}

// ---------------------------------------------------------------- Win32 UI 文字（language.txt 經引擎轉成 CP932＋隧道碼後以 A 版 API 顯示）
typedef int (WINAPI *MBA_t)(HWND, LPCSTR, LPCSTR, UINT);
typedef int (WINAPI *MBW_t)(HWND, LPCWSTR, LPCWSTR, UINT);
typedef BOOL (WINAPI *SWTA_t)(HWND, LPCSTR);
typedef BOOL (WINAPI *SDITA_t)(HWND, int, LPCSTR);
typedef LRESULT (WINAPI *SMA_t)(HWND, UINT, WPARAM, LPARAM);
static MBA_t o_MBA; static SWTA_t o_SWTA; static SDITA_t o_SDITA; static SMA_t o_SMA;

static int has_high(LPCSTR s) { if (!s || IS_INTRESOURCE(s)) return 0; for (; *s; s++) if ((unsigned char)*s >= 0x80) return 1; return 0; }
// 視窗標題等內建字串的作品名（不改 startup.xml 的 title，以免存檔資料夾路徑改變）
static const WCHAR *g_repl[][2] = {
    { L"\x30B0\x30EA\x30B6\x30A4\x30A2\x306E\x8FF7\x5BAE", L"\x7070\x8272\x7684\x8FF7\x5BAE" },   /* グリザイアの迷宮 → 灰色的迷宮 */
    { L"\x30B0\x30EA\x30B6\x30A4\x30A2\x306E\x65CB\x5F8B", L"\x7070\x8272\x7684\x65CB\x5F8B" },   /* グリザイアの旋律 → 灰色的旋律 */
    { L"\x30D5\x30ED\x30F3\x30C8\x30A6\x30A4\x30F3\x30B0", L"Frontwing" },                               /* フロントウイング */
};
static void apply_repl(WCHAR *w) {
    for (size_t k = 0; k < sizeof g_repl / sizeof g_repl[0]; k++) {
        size_t la = wcslen(g_repl[k][0]), lb = wcslen(g_repl[k][1]);   // lb <= la
        WCHAR *p;
        while ((p = wcsstr(w, g_repl[k][0])) != NULL) { memcpy(p, g_repl[k][1], lb * sizeof(WCHAR)); memmove(p + lb, p + la, (wcslen(p + la) + 1) * sizeof(WCHAR)); }
    }
}
static WCHAR *dup932(LPCSTR s) {
    int n = decode932(0, s, -1, NULL, 0); if (n <= 0) return NULL;
    WCHAR *w = (WCHAR *)HeapAlloc(GetProcessHeap(), 0, (n + 1) * sizeof(WCHAR));
    decode932(0, s, -1, w, n); w[n] = 0; apply_repl(w); return w;
}
static void freew(WCHAR *w) { if (w) HeapFree(GetProcessHeap(), 0, w); }

static int WINAPI h_MBA(HWND h, LPCSTR text, LPCSTR cap, UINT t) {
    if (!from_exe(__builtin_return_address(0))) return o_MBA(h, text, cap, t);
    WCHAR *wt = dup932(text), *wc = dup932(cap);
    logf("MessageBoxA\n"); loghex("text", text, -1);
    int r = MessageBoxW(h, wt ? wt : L"", wc ? wc : NULL, t);
    freew(wt); freew(wc); return r;
}
static BOOL WINAPI h_SWTA(HWND h, LPCSTR s) {
    if (!from_exe(__builtin_return_address(0)) || !has_high(s)) return o_SWTA(h, s);
    WCHAR *w = dup932(s); BOOL r = SetWindowTextW(h, w ? w : L""); freew(w); return r;
}
static BOOL WINAPI h_SDITA(HWND h, int id, LPCSTR s) {
    if (!from_exe(__builtin_return_address(0)) || !has_high(s)) return o_SDITA(h, id, s);
    WCHAR *w = dup932(s); BOOL r = SetDlgItemTextW(h, id, w ? w : L""); freew(w); return r;
}
static LRESULT WINAPI h_SMA(HWND h, UINT msg, WPARAM wp, LPARAM lp) {
    if ((msg == WM_SETTEXT || msg == CB_ADDSTRING || msg == LB_ADDSTRING || msg == CB_INSERTSTRING || msg == LB_INSERTSTRING)
        && from_exe(__builtin_return_address(0)) && has_high((LPCSTR)lp)) {
        WCHAR *w = dup932((LPCSTR)lp); LRESULT r = SendMessageW(h, msg, wp, (LPARAM)w); freew(w); return r;
    }
    return o_SMA(h, msg, wp, lp);
}

typedef HWND (WINAPI *CWEA_t)(DWORD, LPCSTR, LPCSTR, DWORD, int, int, int, int, HWND, HMENU, HINSTANCE, LPVOID);
static CWEA_t o_CWEA;
static void wnd_probe_on_create(HWND h, LPCSTR cls, DWORD style, DWORD ex);
static DWORD win_create_style(LPCSTR cls, DWORD st);
static void win_on_create(HWND h, LPCSTR cls);
static HWND WINAPI h_CWEA(DWORD ex, LPCSTR cls, LPCSTR name, DWORD st, int x, int y, int w, int h, HWND p, HMENU m, HINSTANCE i, LPVOID lp) {
    if (!p && from_exe(__builtin_return_address(0))) st = win_create_style(cls, st);
    HWND r = o_CWEA(ex, cls, name, st, x, y, w, h, p, m, i, lp);
    if (r && has_high(name) && from_exe(__builtin_return_address(0))) { WCHAR *t = dup932(name); if (t) { SetWindowTextW(r, t); freew(t); } }
    if (r && !p) { win_on_create(r, cls); if (!g_win_enable) wnd_probe_on_create(r, cls, st, ex); }
    return r;
}

static void hook(const char *mod, const char *name, void *det, void **orig) {
    HMODULE m = GetModuleHandleA(mod); if (!m) m = LoadLibraryA(mod);
    void *p = m ? (void *)GetProcAddress(m, name) : NULL;
    if (!p) { logf("hook %s!%s: not found\n", mod, name); return; }
    MH_STATUS s1 = MH_CreateHook(p, det, orig);
    MH_STATUS s2 = MH_EnableHook(p);
    logf("hook %s!%s at %p: %d %d\n", mod, name, p, s1, s2);
}

#include "zhtw_diag.c"
#include "zhtw_fs.c"
#include "zhtw_wndprobe.c"
#include "zhtw_window.c"

static void install(void) {
    g_exe = GetModuleHandleW(NULL);
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)g_exe;
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)((BYTE *)g_exe + dos->e_lfanew);
    g_exe_lo = (DWORD_PTR)g_exe; g_exe_hi = g_exe_lo + nt->OptionalHeader.SizeOfImage;
    GetModuleFileNameW(g_exe, g_dir, MAX_PATH);
    wchar_t *p = wcsrchr(g_dir, L'\\'); if (p) *p = 0;
    InitializeCriticalSection(&g_cs);
    load_config();
    logf("zhtw_hook loaded: exe %p-%p acp=%u map=%d font='%s'\n", (void *)g_exe_lo, (void *)g_exe_hi, GetACP(), g_map_count, g_font_face);
    MH_Initialize();
    hook("kernel32.dll", "MultiByteToWideChar", (void *)h_MBTWC, (void **)&o_MBTWC);
    hook("kernel32.dll", "WideCharToMultiByte", (void *)h_WCTMB, (void **)&o_WCTMB);
    hook("gdi32.dll", "GetGlyphOutlineA", (void *)h_GGOA, (void **)&o_GGOA);
    hook("gdi32.dll", "GetGlyphOutlineW", (void *)h_GGOW, (void **)&o_GGOW);
    hook("gdi32.dll", "GetTextExtentPoint32A", (void *)h_GTEPA, (void **)&o_GTEPA);
    hook("gdi32.dll", "CreateFontIndirectA", (void *)h_CFIA, (void **)&o_CFIA);
    hook("gdi32.dll", "GetTextMetricsA", (void *)h_GTMA, (void **)&o_GTMA);
    hook("user32.dll", "CreateWindowExA", (void *)h_CWEA, (void **)&o_CWEA);
    hook("user32.dll", "MessageBoxA", (void *)h_MBA, (void **)&o_MBA);
    hook("user32.dll", "SetWindowTextA", (void *)h_SWTA, (void **)&o_SWTA);
    hook("user32.dll", "SetDlgItemTextA", (void *)h_SDITA, (void **)&o_SDITA);
    hook("user32.dll", "SendMessageA", (void *)h_SMA, (void **)&o_SMA);
    if (!o_GGOW) o_GGOW = (GGOW_t)GetProcAddress(GetModuleHandleA("gdi32.dll"), "GetGlyphOutlineW");
    o_GTEPW = (GTEPW_t)GetProcAddress(GetModuleHandleA("gdi32.dll"), "GetTextExtentPoint32W");
    fs_install();
    if (g_win_enable) win_install(); else wnd_probe_install();
    diag_install();
}

// ---------------------------------------------------------------- version.dll forwarding
static HMODULE g_ver;
static FARPROC realp(const char *n) {
    if (!g_ver) {
        wchar_t sys[MAX_PATH]; GetSystemDirectoryW(sys, MAX_PATH); wcscat(sys, L"\\version.dll");
        g_ver = LoadLibraryW(sys);
    }
    return g_ver ? GetProcAddress(g_ver, n) : NULL;
}
#define FWD(ret, name, params, args) \
    ret WINAPI px_##name params { \
        typedef ret (WINAPI *T) params; static T fp_; if (!fp_) fp_ = (T)realp(#name); \
        return fp_ ? fp_ args : (ret)0; }

FWD(BOOL, GetFileVersionInfoA, (LPCSTR a, DWORD b, DWORD c, LPVOID d), (a, b, c, d))
FWD(BOOL, GetFileVersionInfoW, (LPCWSTR a, DWORD b, DWORD c, LPVOID d), (a, b, c, d))
FWD(BOOL, GetFileVersionInfoExA, (DWORD f0, LPCSTR a, DWORD b, DWORD c, LPVOID d), (f0, a, b, c, d))
FWD(BOOL, GetFileVersionInfoExW, (DWORD f0, LPCWSTR a, DWORD b, DWORD c, LPVOID d), (f0, a, b, c, d))
FWD(DWORD, GetFileVersionInfoSizeA, (LPCSTR a, LPDWORD b), (a, b))
FWD(DWORD, GetFileVersionInfoSizeW, (LPCWSTR a, LPDWORD b), (a, b))
FWD(DWORD, GetFileVersionInfoSizeExA, (DWORD f0, LPCSTR a, LPDWORD b), (f0, a, b))
FWD(DWORD, GetFileVersionInfoSizeExW, (DWORD f0, LPCWSTR a, LPDWORD b), (f0, a, b))
FWD(BOOL, GetFileVersionInfoByHandle, (DWORD a, HANDLE b, LPVOID c, DWORD d), (a, b, c, d))
FWD(DWORD, VerFindFileA, (DWORD a, LPCSTR b, LPCSTR c, LPCSTR d, LPSTR e, PUINT f, LPSTR g, PUINT h), (a, b, c, d, e, f, g, h))
FWD(DWORD, VerFindFileW, (DWORD a, LPCWSTR b, LPCWSTR c, LPCWSTR d, LPWSTR e, PUINT f, LPWSTR g, PUINT h), (a, b, c, d, e, f, g, h))
FWD(DWORD, VerInstallFileA, (DWORD a, LPCSTR b, LPCSTR c, LPCSTR d, LPCSTR e, LPCSTR f, LPSTR g, PUINT h), (a, b, c, d, e, f, g, h))
FWD(DWORD, VerInstallFileW, (DWORD a, LPCWSTR b, LPCWSTR c, LPCWSTR d, LPCWSTR e, LPCWSTR f, LPWSTR g, PUINT h), (a, b, c, d, e, f, g, h))
FWD(DWORD, VerLanguageNameA, (DWORD a, LPSTR b, DWORD c), (a, b, c))
FWD(DWORD, VerLanguageNameW, (DWORD a, LPWSTR b, DWORD c), (a, b, c))
FWD(BOOL, VerQueryValueA, (LPCVOID a, LPCSTR b, LPVOID *c, PUINT d), (a, b, c, d))
FWD(BOOL, VerQueryValueW, (LPCVOID a, LPCWSTR b, LPVOID *c, PUINT d), (a, b, c, d))

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID r) {
    if (reason == DLL_PROCESS_ATTACH) { g_self = h; DisableThreadLibraryCalls(h); install(); }
    return TRUE;
}
