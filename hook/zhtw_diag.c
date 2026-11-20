// ---------------------------------------------------------------- 結束流程診斷（[diag] exit=1）
// 記錄 PostQuitMessage／DestroyWindow／ExitProcess 的呼叫時間；結束開始後 3 秒與 10 秒
// 各把所有執行緒的 EIP 與堆疊上指向模組程式碼的位址記到 log（先全部暫停複製，恢復後才解析與寫檔，避免死鎖）。
#include <tlhelp32.h>
// g_diag_exit／g_fast_exit 宣告於 zhtw_hook.c 前段
static volatile LONG g_exit_t0 = 0;   // GetTickCount() 的結束起點（0＝尚未開始）
static volatile LONG g_exit_seen = 0;
typedef BOOL (WINAPI *DW_t)(HWND); typedef VOID (WINAPI *PQM_t)(int); typedef VOID (WINAPI *EP_t)(UINT);
static DW_t o_DW; static PQM_t o_PQM; static EP_t o_EP;

static void exit_mark(const char *what) {
    if (!g_exit_t0) InterlockedCompareExchange(&g_exit_t0, (LONG)(GetTickCount() | 1), 0);
    logf("[exit] %s tid=%lu t=%lu\n", what, GetCurrentThreadId(), GetTickCount());
}
static BOOL WINAPI h_DW(HWND h) {
    if (!GetParent(h)) { char cls[64] = ""; GetClassNameA(h, cls, 64); logf("[exit] DestroyWindow top-level %p class=%s\n", h, cls); exit_mark("DestroyWindow"); }
    BOOL r = o_DW(h);
    if (!GetParent(h)) logf("[exit] DestroyWindow returned %d t=%lu\n", r, GetTickCount());
    return r;
}
static VOID WINAPI h_PQM(int code) { exit_mark("PostQuitMessage"); o_PQM(code); }
static VOID WINAPI h_EP(UINT code) {
    exit_mark("ExitProcess");
    if (g_fast_exit) { logf("[exit] fast_exit -> TerminateProcess(%u)\n", code); TerminateProcess(GetCurrentProcess(), code); }
    o_EP(code);
}

#define DIAG_MAXT 64
#define DIAG_WORDS 2048
typedef struct { DWORD tid, eip, esp, ebp, n; DWORD w[DIAG_WORDS]; } TSnap;
static TSnap g_snap[DIAG_MAXT];

typedef struct { DWORD lo, hi; char name[64]; } ModR;
static ModR g_mods[256]; static int g_nmods;
static void load_modules(void) {
    HMODULE hm[256]; DWORD need = 0; g_nmods = 0;
    typedef BOOL (WINAPI *EPM)(HANDLE, HMODULE *, DWORD, LPDWORD);
    typedef DWORD (WINAPI *GMFN)(HANDLE, HMODULE, LPSTR, DWORD);
    typedef struct { LPVOID base; DWORD size; LPVOID entry; } MI;
    typedef BOOL (WINAPI *GMI)(HANDLE, HMODULE, MI *, DWORD);
    HMODULE k = GetModuleHandleA("kernel32.dll");
    EPM epm = (EPM)GetProcAddress(k, "K32EnumProcessModules");
    GMFN gmfn = (GMFN)GetProcAddress(k, "K32GetModuleBaseNameA");
    GMI gmi = (GMI)GetProcAddress(k, "K32GetModuleInformation");
    if (!epm || !gmfn || !gmi || !epm(GetCurrentProcess(), hm, sizeof hm, &need)) return;
    int n = (int)(need / sizeof(HMODULE)); if (n > 256) n = 256;
    for (int i = 0; i < n; i++) {
        MI mi; if (!gmi(GetCurrentProcess(), hm[i], &mi, sizeof mi)) continue;
        ModR *m = &g_mods[g_nmods++];
        m->lo = (DWORD)(DWORD_PTR)mi.base; m->hi = m->lo + mi.size;
        if (!gmfn(GetCurrentProcess(), hm[i], m->name, sizeof m->name)) strcpy(m->name, "?");
    }
}
static const ModR *mod_of(DWORD a) { for (int i = 0; i < g_nmods; i++) if (a >= g_mods[i].lo && a < g_mods[i].hi) return &g_mods[i]; return NULL; }
static int readable(DWORD a, DWORD n) {
    MEMORY_BASIC_INFORMATION mb;
    if (!VirtualQuery((LPCVOID)(DWORD_PTR)a, &mb, sizeof mb) || mb.State != MEM_COMMIT) return 0;
    if (mb.Protect & (PAGE_NOACCESS | PAGE_GUARD)) return 0;
    return a + n <= (DWORD)(DWORD_PTR)mb.BaseAddress + (DWORD)mb.RegionSize;
}
static int is_code(DWORD a) {
    MEMORY_BASIC_INFORMATION mb;
    if (!VirtualQuery((LPCVOID)(DWORD_PTR)a, &mb, sizeof mb)) return 0;
    return mb.State == MEM_COMMIT && (mb.Protect & (PAGE_EXECUTE | PAGE_EXECUTE_READ | PAGE_EXECUTE_READWRITE | PAGE_EXECUTE_WRITECOPY));
}
// 最近的匯出名稱（只讀模組記憶體，不呼叫 loader）
static const char *near_export(const ModR *m, DWORD a, DWORD *off) {
    BYTE *b = (BYTE *)(DWORD_PTR)m->lo; DWORD rva = a - m->lo, best = 0; const char *bn = NULL;
    {
        if (!readable(m->lo, 0x400)) return NULL;
        IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(b + ((IMAGE_DOS_HEADER *)b)->e_lfanew);
        IMAGE_DATA_DIRECTORY *dd = &nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_EXPORT];
        if (!dd->VirtualAddress || !readable(m->lo + dd->VirtualAddress, sizeof(IMAGE_EXPORT_DIRECTORY))) return NULL;
        IMAGE_EXPORT_DIRECTORY *ed = (IMAGE_EXPORT_DIRECTORY *)(b + dd->VirtualAddress);
        if (!readable(m->lo + ed->AddressOfFunctions, 4 * ed->NumberOfFunctions) || !readable(m->lo + ed->AddressOfNames, 4 * ed->NumberOfNames)) return NULL;
        DWORD *fn = (DWORD *)(b + ed->AddressOfFunctions), *nm = (DWORD *)(b + ed->AddressOfNames);
        WORD *ord = (WORD *)(b + ed->AddressOfNameOrdinals);
        for (DWORD i = 0; i < ed->NumberOfNames; i++) {
            DWORD f = fn[ord[i]];
            if (f <= rva && f > best) { best = f; bn = (const char *)(b + nm[i]); }
        }
    }
    if (bn) *off = rva - best;
    return bn;
}
static void log_addr(const char *tag, DWORD a) {
    const ModR *m = mod_of(a); DWORD off = 0;
    if (!m) { logf("    %s %08lx\n", tag, a); return; }
    const char *e = near_export(m, a, &off);
    if (e && off < 0x4000) logf("    %s %08lx %s!%s+0x%lx\n", tag, a, m->name, e, off);
    else logf("    %s %08lx %s+0x%lx\n", tag, a, m->name, a - m->lo);
}
static void dump_threads(const char *label) {
    DWORD self = GetCurrentThreadId(), pid = GetCurrentProcessId();
    DWORD tids[DIAG_MAXT]; int nt = 0;
    HANDLE sn = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
    if (sn == INVALID_HANDLE_VALUE) { logf("[diag] snapshot failed\n"); return; }
    THREADENTRY32 te; te.dwSize = sizeof te;
    for (BOOL ok = Thread32First(sn, &te); ok && nt < DIAG_MAXT; ok = Thread32Next(sn, &te))
        if (te.th32OwnerProcessID == pid && te.th32ThreadID != self) tids[nt++] = te.th32ThreadID;
    CloseHandle(sn);
    int ns = 0;
    for (int i = 0; i < nt; i++) {   // 暫停期間只做記憶體複製，不配置、不寫檔
        HANDLE th = OpenThread(THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT | THREAD_QUERY_INFORMATION, FALSE, tids[i]);
        if (!th) continue;
        if (SuspendThread(th) == (DWORD)-1) { CloseHandle(th); continue; }
        CONTEXT c; memset(&c, 0, sizeof c); c.ContextFlags = CONTEXT_CONTROL | CONTEXT_INTEGER;
        TSnap *s = &g_snap[ns]; s->tid = tids[i]; s->n = 0;
        if (GetThreadContext(th, &c)) {
            s->eip = c.Eip; s->esp = c.Esp; s->ebp = c.Ebp;
            MEMORY_BASIC_INFORMATION mb;
            if (VirtualQuery((LPCVOID)(DWORD_PTR)c.Esp, &mb, sizeof mb)) {
                DWORD end = (DWORD)(DWORD_PTR)mb.BaseAddress + (DWORD)mb.RegionSize, p = c.Esp & ~3u;
                while (p + 4 <= end && s->n < DIAG_WORDS) { s->w[s->n++] = *(DWORD *)(DWORD_PTR)p; p += 4; }
            }
            ns++;
        }
        ResumeThread(th); CloseHandle(th);
    }
    load_modules();
    logf("[diag] ===== %s: %d threads (t=%lu, exit_t0=%lu) =====\n", label, ns, GetTickCount(), (unsigned long)g_exit_t0);
    for (int i = 0; i < ns; i++) {
        TSnap *s = &g_snap[i];
        logf("  thread %lu eip=%08lx esp=%08lx ebp=%08lx stack=%lu words\n", s->tid, s->eip, s->esp, s->ebp, s->n);
        log_addr("EIP", s->eip);
        int shown = 0;
        for (DWORD k = 0; k < s->n && shown < 24; k++) {
            DWORD v = s->w[k];
            if (v < 0x10000 || !mod_of(v) || !is_code(v)) continue;
            // 回返位址前一個指令通常是 call（E8 rel32 或 FF /2）
            BYTE *q = (BYTE *)(DWORD_PTR)v; int call = 0;
            if (readable(v - 7, 7)) call = (q[-5] == 0xE8) || (q[-6] == 0xFF) || (q[-2] == 0xFF) || (q[-3] == 0xFF) || (q[-7] == 0xFF);
            if (!call) continue;
            char tag[16]; sprintf(tag, "+%03lx", k * 4); log_addr(tag, v); shown++;
        }
    }
}
static DWORD WINAPI diag_thread(LPVOID p) {
    int stage = 0;
    for (;;) {
        Sleep(250);
        LONG t0 = g_exit_t0; if (!t0) continue;
        DWORD dt = GetTickCount() - (DWORD)t0;
        if (stage == 0 && dt > 3000) { dump_threads("exit+3s"); stage = 1; }
        else if (stage == 1 && dt > 10000) { dump_threads("exit+10s"); stage = 2; }
        else if (stage == 2 && dt > 30000) { dump_threads("exit+30s"); return 0; }
    }
}
static void diag_install(void) {
    if (!g_diag_exit && !g_fast_exit) return;
    hook("user32.dll", "DestroyWindow", (void *)h_DW, (void **)&o_DW);
    hook("user32.dll", "PostQuitMessage", (void *)h_PQM, (void **)&o_PQM);
    hook("kernel32.dll", "ExitProcess", (void *)h_EP, (void **)&o_EP);
    if (g_diag_exit) CreateThread(NULL, 0, diag_thread, NULL, 0, NULL);
    logf("[diag] exit=%d fast_exit=%d\n", g_diag_exit, g_fast_exit);
}

