/* LGPL-2.1-or-later. Bound repeated ineffective yields, not useful work.
 * All times are monotonic 100ns units. One state per calling thread. */
#ifndef PES13_FEX_YIELD_BURST_H
#define PES13_FEX_YIELD_BURST_H
#include <stdint.h>

struct fex_yield_burst { uint64_t first; unsigned count; };

static inline int fex_yield_pause_due(struct fex_yield_burst *s,
                                    uint64_t begin, uint64_t end)
{
    /* A yield that consumed >=2us may have run a peer. Do not add a pause. */
    if (end < begin || end - begin >= 20) {
        s->count = 0;
        return 0;
    }
    /* Ordinary yields, or calls spread over frames, cannot accumulate. */
    if (!s->count || begin < s->first || end - s->first > 20000) {
        s->first = begin;
        s->count = 0;
    }
    if (++s->count < 64) return 0;
    s->count = 0;
    return 1;
}
#endif
