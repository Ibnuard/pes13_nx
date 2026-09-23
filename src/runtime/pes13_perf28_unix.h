/* Included after read_guest(), called only after wine_nx_box64_run unwinds. */
#ifdef __SWITCH__
#include "pes13_perf28_fault.h"
extern int wine_nx_perf28_identity(void);
extern void wine_nx_runtime_trace(const char *);
static int pes28_guest_read(void *opaque, uint32_t at, void *out, size_t size)
{
    return read_guest(opaque, at, out, size) == STATUS_SUCCESS;
}
static void pes28_guest_emit(void *opaque, const char *line)
{
    (void)opaque; wine_nx_runtime_trace(line);
}
static void pes28_after_run(NTSTATUS status, const struct winebox64_run_params *p)
{
    static unsigned int captured;
    /* Successful calls pay only this status test, with no memory reads. */
    if (status != STATUS_ACCESS_VIOLATION || !p->context) return;
    const WOW64_CONTEXT *c = p->context;
    const struct pes28_fault f = {
        (uint32_t)status, p->fault_address, p->fault_access,
        c->Eip, c->Esp, c->Eax, c->Ebx, c->Ecx, c->Edx, c->Esi, c->Edi, c->Ebp,
        wine_nx_perf28_identity()
    };
    const struct pes28_io io = { pes28_guest_read, pes28_guest_emit, NULL };
    pes28_capture(&captured, &f, &io);
}
#endif
