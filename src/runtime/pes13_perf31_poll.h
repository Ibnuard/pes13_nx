/* Only optional error-notification scans after a zero-time fence timeout.
 * Native fence completion is always queried first. Never caches completion. */
#ifndef PES13_PERF31_POLL_H
#define PES13_PERF31_POLL_H
#include <stdint.h>
struct pes31_poll_gate { uintptr_t device; uint64_t checked_ns; unsigned syncpoint, valid; };
static int pes31_defer_error_scan(struct pes31_poll_gate *g, uintptr_t device,
                                 unsigned syncpoint, uint64_t timeout_ns, uint64_t now_ns, int enabled)
{
    if (!enabled || timeout_ns != 0) return 0;
    if (g->valid && g->device == device && g->syncpoint == syncpoint && now_ns >= g->checked_ns &&
        now_ns - g->checked_ns < UINT64_C(50000000)) return 1;
    g->device=device; g->syncpoint=syncpoint; g->checked_ns=now_ns; g->valid=1;
    return 0;
}
#endif
