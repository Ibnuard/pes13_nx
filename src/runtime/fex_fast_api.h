/* LGPL-2.1-or-later. Two-argument ARM64 syscall gateway, not a new clock
 * or wait implementation. Selected only after live service-table validation.
 * Entry keeps Wine's existing WOW64 exception boundary and pending work. */
int wine_nx_fex_fast_api = 0; /* startup config; control defaults to old path */

static void fex_fast_api_count(unsigned id)
{
    if (!fex_poll_count_kind(id, 1)) {
        __atomic_add_fetch(&wine_nx_syscalls, 1, __ATOMIC_RELAXED);
        __atomic_add_fetch(&wine_nx_syscall_counts[id], 1, __ATOMIC_RELAXED);
    }
}

__attribute__((used, noinline))
NTSTATUS wine_nx_fex_fast_qpc(LARGE_INTEGER *counter, LARGE_INTEGER *frequency)
{
    fex_fast_api_count(FEX_POLL_QPC);
    return NtQueryPerformanceCounter(counter, frequency);
}

__attribute__((used, noinline))
NTSTATUS wine_nx_fex_fast_delay(BOOLEAN alertable, const LARGE_INTEGER *timeout)
{
    fex_fast_api_count(FEX_POLL_DELAY);
    return NtDelayExecution(alertable, timeout);
}

/* x0-x8 and the PE caller's return address x9 remain intact on every reject.
 * No native call occurs before x18 (Wine TEB) has been saved. QPC/delay cannot
 * replace a thread's TEB; restoring that saved value avoids a TLS lookup.
 * All handler arguments and error/SEH behavior remain in the original Wine
 * handlers. Native code is built with the platform's fixed-x18 convention. */
C_ASSERT(offsetof(SYSTEM_SERVICE_TABLE, ServiceTable) == 0);
C_ASSERT(offsetof(SYSTEM_SERVICE_TABLE, ServiceLimit) == 16);
#define FEX_FAST_API_ENTRY \
    "    cmp w8, #0x31\n" \
    "    b.eq .Lfex_api_probe\n" \
    "    cmp w8, #0x34\n" \
    "    b.ne .Lfex_api_slow\n" \
    ".Lfex_api_probe:\n" \
    "    adrp x16, wine_nx_fex_fast_api\n" \
    "    ldr w16, [x16, :lo12:wine_nx_fex_fast_api]\n" \
    "    cbz w16, .Lfex_api_slow\n" \
    "    adrp x16, wine_nx_runtime_verbose\n" \
    "    ldr w16, [x16, :lo12:wine_nx_runtime_verbose]\n" \
    "    cbnz w16, .Lfex_api_slow\n" \
    "    adrp x16, KeServiceDescriptorTable\n" \
    "    add x16, x16, :lo12:KeServiceDescriptorTable\n" \
    "    ldr x17, [x16, #16]\n" \
    "    cmp x17, w8, uxtw\n" \
    "    b.ls .Lfex_api_slow\n" \
    "    ldr x16, [x16]\n" \
    "    cbz x16, .Lfex_api_slow\n" \
    "    ldr x16, [x16, w8, uxtw #3]\n" \
    "    cmp w8, #0x31\n" \
    "    b.ne .Lfex_api_delay_check\n" \
    "    adrp x17, NtQueryPerformanceCounter\n" \
    "    add x17, x17, :lo12:NtQueryPerformanceCounter\n" \
    "    cmp x16, x17\n" \
    "    b.ne .Lfex_api_slow\n" \
    "    stp x29, x9, [sp, #-32]!\n" \
    "    mov x29, sp\n" \
    "    str x18, [sp, #16]\n" \
    "    bl wine_nx_fex_fast_qpc\n" \
    "    b .Lfex_api_return\n" \
    ".Lfex_api_delay_check:\n" \
    "    cbnz w0, .Lfex_api_slow\n" \
    "    adrp x17, NtDelayExecution\n" \
    "    add x17, x17, :lo12:NtDelayExecution\n" \
    "    cmp x16, x17\n" \
    "    b.ne .Lfex_api_slow\n" \
    "    stp x29, x9, [sp, #-32]!\n" \
    "    mov x29, sp\n" \
    "    str x18, [sp, #16]\n" \
    "    bl wine_nx_fex_fast_delay\n" \
    ".Lfex_api_return:\n" \
    "    ldr x18, [sp, #16]\n" \
    "    ldp x29, x30, [sp], #32\n" \
    "    ret\n" \
    ".Lfex_api_slow:\n"
