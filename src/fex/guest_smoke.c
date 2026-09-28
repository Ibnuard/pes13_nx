/* SPDX-License-Identifier: MIT
 * Original i386 guest, no game code and no CRT. Each checkpoint is persisted
 * before advancing so a hardware failure identifies the last completed test.
 */
#include <windows.h>
#include <emmintrin.h>
#include <stdint.h>
int _fltused;
static HANDLE report;
static DWORD tls_slot;
static void *main_teb;
static volatile LONG worker_ok;

static void line(const char *text)
{
    DWORD bytes = 0, written;
    while (text[bytes]) ++bytes;
    if (!WriteFile(report, text, bytes, &written, NULL) || written != bytes ||
        !FlushFileBuffers(report)) ExitProcess(90);
}

static void check(int passed, const char *pass, const char *fail)
{
    line(passed ? pass : fail);
    if (!passed) ExitProcess(1);
}

static DWORD WINAPI worker(void *unused)
{
    void *teb;
    (void)unused;
    __asm__ volatile("movl %%fs:0x18, %0" : "=r"(teb));
    if (!teb || teb == main_teb || TlsGetValue(tls_slot) != NULL) return 1;
    if (!TlsSetValue(tls_slot, (void *)0x5678) || TlsGetValue(tls_slot) != (void *)0x5678) return 2;
    InterlockedExchange(&worker_ok, 1);
    return 0;
}

__declspec(noreturn) void probe_entry(void)
{
    DWORD old_protection, tid, exit_code;
    HANDLE thread;
    unsigned char *code;
    int (*function)(void);
    SIZE_T size = 4096;
    FILETIME before, after;
    volatile LONG a = 123, b = 456;
    volatile float value = 2.0f;
    float vector[4];
    double root;
    int input = 81;
    report = CreateFileA("fex-guest.log", GENERIC_WRITE, FILE_SHARE_READ, NULL,
                         CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (report == INVALID_HANDLE_VALUE) ExitProcess(91);
    line("[FEX2-GUEST] entered original x86 executable\r\n");
    check(a * b == 56088 && ((a << 5) ^ b) == 3752,
          "PASS integer arithmetic\r\n", "FAIL integer arithmetic\r\n");
    __asm__ volatile("movl %%fs:0x18, %0" : "=r"(main_teb));
    tls_slot = TlsAlloc();
    check(main_teb != NULL && tls_slot != TLS_OUT_OF_INDEXES &&
          TlsSetValue(tls_slot, (void *)0x1234) && TlsGetValue(tls_slot) == (void *)0x1234,
          "PASS FS and TLS\r\n", "FAIL FS and TLS\r\n");
    _mm_storeu_ps(vector, _mm_add_ps(_mm_mul_ps(_mm_set1_ps(value), _mm_set1_ps(value)), _mm_set1_ps(value)));
    check(vector[0] == 6.0f && vector[1] == 6.0f && vector[2] == 6.0f && vector[3] == 6.0f,
          "PASS SSE arithmetic\r\n", "FAIL SSE arithmetic\r\n");
    __asm__ volatile("fildl %1; fsqrt; fstpl %0" : "=m"(root) : "m"(input) : "st");
    check(root == 9.0, "PASS x87 arithmetic\r\n", "FAIL x87 arithmetic\r\n");
    GetSystemTimeAsFileTime(&before);
    Sleep(20);
    GetSystemTimeAsFileTime(&after);
    check(after.dwHighDateTime > before.dwHighDateTime ||
          (after.dwHighDateTime == before.dwHighDateTime && after.dwLowDateTime > before.dwLowDateTime),
          "PASS clock and wait syscall\r\n", "FAIL clock and wait syscall\r\n");
    code = VirtualAlloc(NULL, size, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    check(code != NULL, "PASS guest allocation\r\n", "FAIL guest allocation\r\n");
    code[0] = 0xb8; code[1] = 42; code[2] = code[3] = code[4] = 0; code[5] = 0xc3;
    function = (void *)code;
    check(VirtualProtect(code, size, PAGE_EXECUTE_READ, &old_protection) &&
          FlushInstructionCache(GetCurrentProcess(), code, 6) && function() == 42,
          "PASS guest executable mapping and CALL/RET\r\n", "FAIL guest code execution\r\n");
    check(VirtualProtect(code, size, PAGE_READWRITE, &old_protection),
          "PASS executable to writable\r\n", "FAIL writable transition\r\n");
    code[1] = 85;
    check(VirtualProtect(code, size, PAGE_EXECUTE_READ, &old_protection) &&
          FlushInstructionCache(GetCurrentProcess(), code, 6) && function() == 85,
          "PASS guest code invalidation 42->85\r\n", "FAIL stale translated guest code\r\n");
    check(VirtualFree(code, 0, MEM_RELEASE), "PASS guest release\r\n", "FAIL guest release\r\n");
    thread = CreateThread(NULL, 0, worker, NULL, 0, &tid);
    check(thread != NULL, "PASS create x86 worker\r\n", "FAIL create x86 worker\r\n");
    check(WaitForSingleObject(thread, 10000) == WAIT_OBJECT_0 &&
          GetExitCodeThread(thread, &exit_code) && exit_code == 0 && worker_ok == 1 &&
          TlsGetValue(tls_slot) == (void *)0x1234,
          "PASS worker TLS isolation and teardown\r\n", "FAIL worker TLS or wait\r\n");
    CloseHandle(thread);
    TlsFree(tls_slot);
    line("[FEX2-GUEST] PASS all checks\r\n");
    CloseHandle(report);
    ExitProcess(0);
}
