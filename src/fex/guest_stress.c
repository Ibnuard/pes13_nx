/* SPDX-License-Identifier: MIT
 * Original i386 FEX3 workload: concurrent JIT/SMC, handled guest faults, TLS,
 * waitable workers, and repeated thread teardown. No CRT or game code.
 */
#include <windows.h>
#include <emmintrin.h>
#include <stdint.h>
int _fltused;
#define WORKERS 4
#define WAVES 4
#define ROUNDS 16
static HANDLE report, begin_event;
static DWORD tls_slot;
static void *main_teb;
static volatile LONG handler_entries;
struct worker_state {
    unsigned id, wave, faults, completed;
    volatile LONG phase, active_round;
    volatile LONG handler_calls, handler_phase;
    volatile LONG exception_code, exception_eip, exception_address, exception_access, exception_target;
    unsigned smc_round, smc_expected, smc_actual, smc_stored, smc_protect;
    void *teb, *guard;
    unsigned char *code;
};
static struct worker_state states[WORKERS];

static void line(const char *s)
{
    DWORD n = 0, written;
    while (s[n]) ++n;
    if (!WriteFile(report, s, n, &written, NULL) || written != n || !FlushFileBuffers(report)) ExitProcess(90);
}
static void check(int passed, const char *message)
{
    if (!passed) { line(message); ExitProcess(1); }
}
static void hex_result(DWORD value)
{
    char s[] = "worker result=0x00000000\r\n";
    const char *digits = "0123456789abcdef";
    unsigned i;
    for (i = 0; i < 8; ++i) s[16+i] = digits[(value >> (28-4*i)) & 15];
    line(s);
}
static void field(const char *name, DWORD value)
{
    char text[80], *p = text;
    unsigned i;
    while (*name) *p++ = *name++;
    *p++ = '='; *p++ = '0'; *p++ = 'x';
    for (i = 0; i < 8; ++i) *p++ = "0123456789abcdef"[(value >> (28-4*i)) & 15];
    *p++ = '\r'; *p++ = '\n'; *p = 0;
    line(text);
}

static LONG CALLBACK handler(EXCEPTION_POINTERS *p)
{
    struct worker_state *s;
    InterlockedIncrement(&handler_entries);
    s = TlsGetValue(tls_slot);
    if (!s || s == (void *)0x1234) return EXCEPTION_CONTINUE_SEARCH;
    InterlockedIncrement(&s->handler_calls);
    InterlockedExchange(&s->exception_code, p->ExceptionRecord->ExceptionCode);
    InterlockedExchange(&s->exception_eip, p->ContextRecord->Eip);
    InterlockedExchange(&s->exception_address, (uintptr_t)p->ExceptionRecord->ExceptionAddress);
    InterlockedExchange(&s->exception_access, p->ExceptionRecord->NumberParameters >= 1 ? p->ExceptionRecord->ExceptionInformation[0] : 0xffffffff);
    InterlockedExchange(&s->exception_target, p->ExceptionRecord->NumberParameters >= 2 ? p->ExceptionRecord->ExceptionInformation[1] : 0xffffffff);
    InterlockedExchange(&s->handler_phase, 1); /* entered, snapshot ready */
    if (!s->code ||
        p->ExceptionRecord->ExceptionCode != EXCEPTION_ACCESS_VIOLATION ||
        p->ExceptionRecord->ExceptionAddress != s->code + 64 ||
        p->ExceptionRecord->NumberParameters < 2 ||
        p->ExceptionRecord->ExceptionInformation[0] != 0 ||
        p->ExceptionRecord->ExceptionInformation[1] != (uintptr_t)s->guard ||
        p->ContextRecord->Eip != (uintptr_t)s->code + 64) {
        InterlockedExchange(&s->handler_phase, 2); /* rejected unexpected exception */
        return EXCEPTION_CONTINUE_SEARCH;
    }
    ++s->faults;
    p->ContextRecord->Eip += 5; /* original A1 moffs32; return a deterministic value */
    p->ContextRecord->Eax = 0x13579bdf;
    InterlockedExchange(&s->handler_phase, 3); /* accepted; continuing modified context */
    return EXCEPTION_CONTINUE_EXECUTION;
}

static DWORD WINAPI worker(void *argument)
{
    struct worker_state *s = argument;
    DWORD old;
    unsigned i, value;
    int (*call)(void), (*fault)(void);
    __asm__ volatile("movl %%fs:0x18, %0" : "=r"(s->teb));
    if (!s->teb || s->teb == main_teb || TlsGetValue(tls_slot) || !TlsSetValue(tls_slot, s)) return 10;
    InterlockedExchange(&s->phase, 1); /* TLS ready, waiting for start */
    if (WaitForSingleObject(begin_event, 10000) != WAIT_OBJECT_0) return 11;
    InterlockedExchange(&s->phase, 2); /* allocating/protecting test memory */
    s->code = VirtualAlloc(NULL, 4096, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    s->guard = VirtualAlloc(NULL, 4096, MEM_RESERVE | MEM_COMMIT, PAGE_NOACCESS);
    if (!s->code || !s->guard) return 12;
    s->code[0] = 0xb8; s->code[5] = 0xc3;
    s->code[64] = 0xa1; *(uint32_t *)(s->code+65) = (uintptr_t)s->guard; s->code[69] = 0xc3;
    *(uint32_t *)(s->code+1) = 42;
    if (!VirtualProtect(s->code, 4096, PAGE_EXECUTE_READWRITE, &old) ||
        !FlushInstructionCache(GetCurrentProcess(), s->code, 70)) return 13;
    call = (void *)s->code;
    fault = (void *)(s->code+64);
    InterlockedExchange(&s->phase, 3); /* entering original generated code */
    if (call() != 42) return 14;
    InterlockedExchange(&s->phase, 4); /* original code passed */
    for (i = 0; i < ROUNDS; ++i)
    {
        volatile float n = (float)(i+1);
        float vector[4];
        double root;
        int input = 81;
        _mm_storeu_ps(vector, _mm_mul_ps(_mm_set1_ps(n), _mm_set1_ps(2.0f)));
        __asm__ volatile("fildl %1; fsqrt; fstpl %0" : "=m"(root) : "m"(input) : "st");
        if (vector[0] != 2.0f*n || vector[3] != 2.0f*n || root != 9.0) return 15;
        value = 0x1000 + s->wave*1024 + s->id*64 + i;
        InterlockedExchange(&s->active_round, i);
        InterlockedExchange(&s->phase, 5); /* modifying/re-entering code */
        /* Automatic SMC detection: intentionally no FlushInstructionCache
         * between writes to already translated RWX guest code. */
        *(volatile uint32_t *)(s->code+1) = value;
        s->smc_actual = (unsigned)call();
        if (s->smc_actual != value) {
            MEMORY_BASIC_INFORMATION info;
            s->smc_round = i;
            s->smc_expected = value;
            s->smc_stored = *(volatile uint32_t *)(s->code+1);
            s->smc_protect = VirtualQuery(s->code, &info, sizeof(info)) ? info.Protect : 0;
            return 16;
        }
        InterlockedExchange(&s->phase, 6); /* entering handled guest fault */
        if ((unsigned)fault() != 0x13579bdf || s->faults != i+1) return 17;
        if (TlsGetValue(tls_slot) != s) return 18;
        ++s->completed;
        InterlockedExchange(&s->phase, 7); /* iteration passed */
        Sleep(1);
    }
    if (!VirtualFree(s->guard, 0, MEM_RELEASE) || !VirtualFree(s->code, 0, MEM_RELEASE)) return 19;
    s->guard = NULL; s->code = NULL;
    InterlockedExchange(&s->phase, 8); /* workload complete, thread returning */
    return 0;
}

__declspec(noreturn) void probe_entry(void)
{
    HANDLE threads[WORKERS];
    DWORD ids[WORKERS], code;
    unsigned wave, i, j;
    void *veh;
    report = CreateFileA("fex-guest.log", GENERIC_WRITE, FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (report == INVALID_HANDLE_VALUE) ExitProcess(91);
    line("[FEX3-GUEST] v4 begin concurrent guest stress (exception-route diagnostics)\r\n");
    __asm__ volatile("movl %%fs:0x18, %0" : "=r"(main_teb));
    tls_slot = TlsAlloc();
    check(main_teb && tls_slot != TLS_OUT_OF_INDEXES && TlsSetValue(tls_slot, (void *)0x1234), "FAIL main TLS\r\n");
    veh = AddVectoredExceptionHandler(1, handler);
    check(veh != NULL, "FAIL install vectored exception handler\r\n");
    line("PASS guest exception handler registered\r\n");
    for (wave = 0; wave < WAVES; ++wave)
    {
        begin_event = CreateEventA(NULL, TRUE, FALSE, NULL);
        check(begin_event != NULL, "FAIL create start event\r\n");
        for (i = 0; i < WORKERS; ++i)
        {
            states[i] = (struct worker_state){.id=i, .wave=wave};
            threads[i] = CreateThread(NULL, 0, worker, &states[i], 0, &ids[i]);
            check(threads[i] != NULL, "FAIL create worker\r\n");
        }
        check(SetEvent(begin_event), "FAIL release workers\r\n");
        line("[FEX3-GUEST] wave started: 4 workers, SMC and handled access violations\r\n");
        for (i = 0; i < WORKERS; ++i)
        {
            if (WaitForSingleObject(threads[i], 30000) != WAIT_OBJECT_0) {
                line("[FEX3-GUEST] worker deadline; atomic progress snapshots\r\n");
                field("all handler entries", InterlockedCompareExchange(&handler_entries, 0, 0));
                for (j = 0; j < WORKERS; ++j) {
                    field("worker", j);
                    field("phase", InterlockedCompareExchange(&states[j].phase, 0, 0));
                    field("round", InterlockedCompareExchange(&states[j].active_round, 0, 0));
                    field("handler calls", InterlockedCompareExchange(&states[j].handler_calls, 0, 0));
                    field("handler phase", InterlockedCompareExchange(&states[j].handler_phase, 0, 0));
                    field("exception code", InterlockedCompareExchange(&states[j].exception_code, 0, 0));
                    field("exception EIP", InterlockedCompareExchange(&states[j].exception_eip, 0, 0));
                    field("exception address", InterlockedCompareExchange(&states[j].exception_address, 0, 0));
                    field("exception access", InterlockedCompareExchange(&states[j].exception_access, 0, 0));
                    field("exception target", InterlockedCompareExchange(&states[j].exception_target, 0, 0));
                }
                check(0, "FAIL worker deadline\r\n");
            }
            check(GetExitCodeThread(threads[i], &code), "FAIL worker exit status\r\n");
            if (code) {
                hex_result(code);
                field("worker", i); field("wave", wave);
                field("completed", states[i].completed); field("faults", states[i].faults);
                if (code == 16) {
                    field("SMC round", states[i].smc_round);
                    field("SMC code", (uintptr_t)states[i].code);
                    field("SMC expected", states[i].smc_expected);
                    field("SMC actual", states[i].smc_actual);
                    field("SMC stored", states[i].smc_stored);
                    field("SMC Wine protection", states[i].smc_protect);
                }
                check(0, "FAIL worker workload\r\n");
            }
            check(states[i].completed == ROUNDS && states[i].faults == ROUNDS, "FAIL lost work or fault\r\n");
            for (j = 0; j < i; ++j) check(states[j].teb != states[i].teb, "FAIL shared worker TEB\r\n");
            CloseHandle(threads[i]);
        }
        CloseHandle(begin_event);
        check(TlsGetValue(tls_slot) == (void *)0x1234, "FAIL main TLS changed\r\n");
        line("PASS wave: math, TLS, automatic SMC, guest exception resume, exit\r\n");
    }
    RemoveVectoredExceptionHandler(veh);
    TlsFree(tls_slot);
    line("[FEX3-GUEST] PASS all checks: 16 workers, 256 SMC updates, 256 handled faults\r\n");
    CloseHandle(report);
    ExitProcess(0);
}
