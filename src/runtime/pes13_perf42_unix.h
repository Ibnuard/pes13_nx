/* Included after read_guest() in wow64_box64_unix.c. Status is checked only
 * after the guest run has unwound; no native signal handler is modified. */
#ifdef __SWITCH__
#include "pes13_perf42_guard.h"
extern int wine_nx_perf42_guard_enabled(void);
extern int wine_nx_perf42_identity(void);
extern void wine_nx_runtime_trace(const char *);

static int pes42_guest_read(void *opaque, uint32_t address, void *out, size_t size)
{
    (void)opaque;
    return read_guest(NULL, address, out, size) == STATUS_SUCCESS;
}

static int pes42_after_run(NTSTATUS status, struct winebox64_run_params *p)
{
    static unsigned int recovered;
    if (status != STATUS_ACCESS_VIOLATION || !p || !p->context ||
        !wine_nx_perf42_guard_enabled() || recovered >= PES42_MAX_RECOVERIES)
        return 0;
    WOW64_CONTEXT *c = p->context;
    struct pes42_fault fault = {
        (uint32_t)status, p->fault_address, p->fault_access,
        c->Eip, c->Esp, c->Eax, c->Esi, c->Ebp, c->Edi,
        wine_nx_perf42_identity()
    };
    uint32_t resume = 0;
    if (!pes42_decide(&fault, pes42_guest_read, NULL, &resume)) return 0;
    unsigned int previous = __atomic_load_n(&recovered, __ATOMIC_RELAXED);
    do {
        if (previous >= PES42_MAX_RECOVERIES) return 0;
    } while (!__atomic_compare_exchange_n(&recovered, &previous, previous + 1,
                                           0, __ATOMIC_RELAXED, __ATOMIC_RELAXED));
    c->Eip = resume;
    unsigned int count = previous + 1;
    char line[160];
    snprintf(line, sizeof line,
             "[BOOT42] missing key=0386 at 0115c36f; skipped empty lookup to 0115c3b9 count=%u",
             count);
    wine_nx_runtime_trace(line);
    return 1;
}
#endif
