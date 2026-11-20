// ---------------------------------------------------------------- 檔案路徑（[fs] enable=1）
#include <stddef.h>
// 存檔資料夾是 %USERPROFILE%\フロントウイング\グリザイアの迷宮 ～グリザイアの旋律～，引擎以 Shift-JIS 位元組
// 呼叫 CreateDirectoryA 等 A 版 API；非日文系統（如 CP950）會把它當成系統代碼頁解讀而失敗（「セーブデータの作成に失敗しました」）。
// 這裡把含高位元組的路徑轉成 Unicode 改呼叫 W 版：已知的系統前綴（使用者資料夾、遊戲資料夾等，系統代碼頁位元組）
// 照系統代碼頁還原，其餘部分以 CP932 解碼。純 ASCII 路徑完全不經手。
// g_fs_enable 宣告於 zhtw_hook.c 前段
typedef struct { char a[MAX_PATH * 2]; WCHAR w[MAX_PATH]; int alen; } FsPrefix;
static FsPrefix g_pref[8]; static int g_npref = -1;
static CRITICAL_SECTION g_fs_cs;

static void fs_add_prefix(const WCHAR *w) {
    if (!w || !*w || g_npref >= 8) return;
    FsPrefix *p = &g_pref[g_npref];
    wcsncpy(p->w, w, MAX_PATH - 1); p->w[MAX_PATH - 1] = 0;
    size_t n = wcslen(p->w); while (n > 0 && (p->w[n - 1] == L'\\' || p->w[n - 1] == L'/')) p->w[--n] = 0;
    int r = o_WCTMB(CP_ACP, 0, p->w, -1, p->a, sizeof p->a, NULL, NULL);
    if (r <= 1) return;
    p->alen = (int)strlen(p->a);
    int hi = 0; for (int i = 0; i < p->alen; i++) if ((unsigned char)p->a[i] >= 0x80) hi = 1;
    if (!hi) return;          // 純 ASCII 前綴不需特別處理（CP932 解碼結果相同）
    g_npref++;
}
static void fs_init_prefixes(void) {
    if (g_npref >= 0) return;
    EnterCriticalSection(&g_fs_cs);
    if (g_npref < 0) {
        g_npref = 0;
        const WCHAR *vars[] = { L"USERPROFILE", L"APPDATA", L"LOCALAPPDATA", L"TEMP", L"TMP", L"PUBLIC" };
        WCHAR buf[MAX_PATH];
        for (int i = 0; i < 6; i++) if (GetEnvironmentVariableW(vars[i], buf, MAX_PATH)) fs_add_prefix(buf);
        fs_add_prefix(g_dir);
        logf("[fs] %d non-ASCII prefixes\n", g_npref);
    }
    LeaveCriticalSection(&g_fs_cs);
}
static int has_high_a(LPCSTR s) { if (!s) return 0; for (; *s; s++) if ((unsigned char)*s >= 0x80) return 1; return 0; }
// 回傳 1 = 已轉換到 out；0 = 不需處理（呼叫原 A 版）
static int fs_a2w(LPCSTR a, WCHAR *out, int cap) {
    if (!g_fs_enable || !has_high_a(a)) return 0;
    fs_init_prefixes();
    int o = 0; LPCSTR rest = a;
    for (int i = 0; i < g_npref; i++) {
        FsPrefix *p = &g_pref[i];
        if (_strnicmp(a, p->a, p->alen) == 0 && (a[p->alen] == '\\' || a[p->alen] == '/' || a[p->alen] == 0)) {
            o = (int)wcslen(p->w); if (o >= cap) return 0;
            wcscpy(out, p->w); rest = a + p->alen; break;
        }
    }
    int n = decode932(0, rest, -1, out + o, cap - o);
    if (n <= 0) return 0;
    return 1;
}
static void fs_w2a(const WCHAR *w, char *out, int cap) {
    if (o_WCTMB(932, 0, w, -1, out, cap, NULL, NULL) <= 0) out[0] = 0;
}

typedef HANDLE (WINAPI *CFA_t)(LPCSTR, DWORD, DWORD, LPSECURITY_ATTRIBUTES, DWORD, DWORD, HANDLE);
typedef BOOL (WINAPI *CDA_t)(LPCSTR, LPSECURITY_ATTRIBUTES);
typedef DWORD (WINAPI *GFAA_t)(LPCSTR);
typedef BOOL (WINAPI *SFAA_t)(LPCSTR, DWORD);
typedef BOOL (WINAPI *DFA_t)(LPCSTR);
typedef BOOL (WINAPI *CPFA_t)(LPCSTR, LPCSTR, BOOL);
typedef BOOL (WINAPI *MVFA_t)(LPCSTR, LPCSTR);
typedef HANDLE (WINAPI *FFFA_t)(LPCSTR, LPWIN32_FIND_DATAA);
typedef BOOL (WINAPI *FNFA_t)(HANDLE, LPWIN32_FIND_DATAA);
static CFA_t o_CFA; static CDA_t o_CDA; static GFAA_t o_GFAA; static SFAA_t o_SFAA; static DFA_t o_DFA;
static CPFA_t o_CPFA; static MVFA_t o_MVFA; static FFFA_t o_FFFA; static FNFA_t o_FNFA;

#define FS_FROM_OK(ret) (from_exe(ret) || in_module((DWORD_PTR)(ret), "cs2conf.dll", &g_conf_lo, &g_conf_hi))
static void fs_log(const char *api, const WCHAR *w, DWORD r) {
    static int n = 0; if (n++ > 200) return;
    logf("[fs] %s '%ls' -> %lu (err %lu)\n", api, w, (unsigned long)r, GetLastError());
}

static HANDLE WINAPI h_CFA(LPCSTR p, DWORD acc, DWORD sh, LPSECURITY_ATTRIBUTES sa, DWORD cd, DWORD fl, HANDLE t) {
    WCHAR w[MAX_PATH * 2];
    if (FS_FROM_OK(__builtin_return_address(0)) && fs_a2w(p, w, MAX_PATH * 2)) {
        HANDLE h = CreateFileW(w, acc, sh, sa, cd, fl, t); DWORD e = GetLastError();
        fs_log("CreateFile", w, h == INVALID_HANDLE_VALUE ? 0 : 1); SetLastError(e); return h;
    }
    return o_CFA(p, acc, sh, sa, cd, fl, t);
}
static BOOL WINAPI h_CDA(LPCSTR p, LPSECURITY_ATTRIBUTES sa) {
    WCHAR w[MAX_PATH * 2];
    if (FS_FROM_OK(__builtin_return_address(0)) && fs_a2w(p, w, MAX_PATH * 2)) {
        BOOL r = CreateDirectoryW(w, sa); DWORD e = GetLastError(); fs_log("CreateDirectory", w, r); SetLastError(e); return r;
    }
    return o_CDA(p, sa);
}
static DWORD WINAPI h_GFAA(LPCSTR p) {
    WCHAR w[MAX_PATH * 2];
    if (FS_FROM_OK(__builtin_return_address(0)) && fs_a2w(p, w, MAX_PATH * 2)) {
        DWORD r = GetFileAttributesW(w); DWORD e = GetLastError(); fs_log("GetFileAttributes", w, r); SetLastError(e); return r;
    }
    return o_GFAA(p);
}
static BOOL WINAPI h_SFAA(LPCSTR p, DWORD a) {
    WCHAR w[MAX_PATH * 2];
    if (FS_FROM_OK(__builtin_return_address(0)) && fs_a2w(p, w, MAX_PATH * 2)) return SetFileAttributesW(w, a);
    return o_SFAA(p, a);
}
static BOOL WINAPI h_DFA(LPCSTR p) {
    WCHAR w[MAX_PATH * 2];
    if (FS_FROM_OK(__builtin_return_address(0)) && fs_a2w(p, w, MAX_PATH * 2)) return DeleteFileW(w);
    return o_DFA(p);
}
static BOOL WINAPI h_CPFA(LPCSTR a, LPCSTR b, BOOL f) {
    WCHAR wa[MAX_PATH * 2], wb[MAX_PATH * 2];
    if (FS_FROM_OK(__builtin_return_address(0)) && (has_high_a(a) || has_high_a(b))) {
        if (!fs_a2w(a, wa, MAX_PATH * 2)) MultiByteToWideChar(CP_ACP, 0, a, -1, wa, MAX_PATH * 2);
        if (!fs_a2w(b, wb, MAX_PATH * 2)) MultiByteToWideChar(CP_ACP, 0, b, -1, wb, MAX_PATH * 2);
        return CopyFileW(wa, wb, f);
    }
    return o_CPFA(a, b, f);
}
static BOOL WINAPI h_MVFA(LPCSTR a, LPCSTR b) {
    WCHAR wa[MAX_PATH * 2], wb[MAX_PATH * 2];
    if (FS_FROM_OK(__builtin_return_address(0)) && (has_high_a(a) || has_high_a(b))) {
        if (!fs_a2w(a, wa, MAX_PATH * 2)) MultiByteToWideChar(CP_ACP, 0, a, -1, wa, MAX_PATH * 2);
        if (!fs_a2w(b, wb, MAX_PATH * 2)) MultiByteToWideChar(CP_ACP, 0, b, -1, wb, MAX_PATH * 2);
        return MoveFileW(wa, wb);
    }
    return o_MVFA(a, b);
}
// FindFirstFileA：以 W 版搜尋，記住 handle，FindNextFileA 遇到這些 handle 也走 W 版
static HANDLE g_fh[32];
static void fd_w2a(const WIN32_FIND_DATAW *w, LPWIN32_FIND_DATAA a) {
    memcpy(a, w, offsetof(WIN32_FIND_DATAA, cFileName));
    fs_w2a(w->cFileName, a->cFileName, MAX_PATH);
    fs_w2a(w->cAlternateFileName, a->cAlternateFileName, 14);
}
static HANDLE WINAPI h_FFFA(LPCSTR p, LPWIN32_FIND_DATAA fd) {
    WCHAR w[MAX_PATH * 2];
    if (FS_FROM_OK(__builtin_return_address(0)) && fs_a2w(p, w, MAX_PATH * 2)) {
        WIN32_FIND_DATAW fw; HANDLE h = FindFirstFileW(w, &fw); DWORD e = GetLastError();
        fs_log("FindFirstFile", w, h == INVALID_HANDLE_VALUE ? 0 : 1);
        if (h != INVALID_HANDLE_VALUE) {
            fd_w2a(&fw, fd);
            EnterCriticalSection(&g_fs_cs);
            for (int i = 0; i < 32; i++) if (!g_fh[i]) { g_fh[i] = h; break; }
            LeaveCriticalSection(&g_fs_cs);
        }
        SetLastError(e); return h;
    }
    return o_FFFA(p, fd);
}
static BOOL WINAPI h_FNFA(HANDLE h, LPWIN32_FIND_DATAA fd) {
    int mine = 0;
    EnterCriticalSection(&g_fs_cs);
    for (int i = 0; i < 32; i++) if (g_fh[i] == h) { mine = 1; break; }
    LeaveCriticalSection(&g_fs_cs);
    if (mine) {
        WIN32_FIND_DATAW fw; BOOL r = FindNextFileW(h, &fw);
        if (r) fd_w2a(&fw, fd);
        else {   // 搜尋結束：釋放記錄（FindClose 仍由遊戲呼叫）
            DWORD e = GetLastError();
            EnterCriticalSection(&g_fs_cs);
            for (int i = 0; i < 32; i++) if (g_fh[i] == h) g_fh[i] = NULL;
            LeaveCriticalSection(&g_fs_cs);
            SetLastError(e);
        }
        return r;
    }
    return o_FNFA(h, fd);
}
static void fs_install(void) {
    if (!g_fs_enable) return;
    InitializeCriticalSection(&g_fs_cs);
    hook("kernel32.dll", "CreateFileA", (void *)h_CFA, (void **)&o_CFA);
    hook("kernel32.dll", "CreateDirectoryA", (void *)h_CDA, (void **)&o_CDA);
    hook("kernel32.dll", "GetFileAttributesA", (void *)h_GFAA, (void **)&o_GFAA);
    hook("kernel32.dll", "SetFileAttributesA", (void *)h_SFAA, (void **)&o_SFAA);
    hook("kernel32.dll", "DeleteFileA", (void *)h_DFA, (void **)&o_DFA);
    hook("kernel32.dll", "CopyFileA", (void *)h_CPFA, (void **)&o_CPFA);
    hook("kernel32.dll", "MoveFileA", (void *)h_MVFA, (void **)&o_MVFA);
    hook("kernel32.dll", "FindFirstFileA", (void *)h_FFFA, (void **)&o_FFFA);
    hook("kernel32.dll", "FindNextFileA", (void *)h_FNFA, (void **)&o_FNFA);
}

