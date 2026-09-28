/* LGPL-2.1-or-later. Reduce sustained polling, never set a CPU utilization cap.
 * Monotonic 100ns units; caller owns one state per thread. */
#ifndef PES13_FEX_YIELD_ADAPTIVE_H
#define PES13_FEX_YIELD_ADAPTIVE_H
#include <stdint.h>

struct fex_yield_adaptive {
    uint64_t first, last, cool_since;
    unsigned count, heat, cooling;
};

/* 0: ordinary yield, 1: initial burst, 2: sustained burst. */
static inline int fex_yield_adaptive_due(struct fex_yield_adaptive *s,
                                       uint64_t begin, uint64_t end)
{
    if (end < begin || (s->last && begin < s->last)) {
        *s = (struct fex_yield_adaptive){0};
        return 0;
    }
    if (s->cooling) {
        s->last = end;
        if (end - s->cool_since < 50000) return 0; /* 5ms after an oversleep */
        s->cooling = 0;
    }
    if (end - begin >= 20) { /* the original yield may have scheduled a peer */
        s->count = s->heat = 0;
        s->last = end;
        return 0;
    }
    if (s->last && begin - s->last > 20000) s->count = s->heat = 0;
    s->last = end;
    if (!s->count || end - s->first > 20000) {
        if (s->count) s->heat = 0;
        s->first = begin;
        s->count = 0;
    }
    if (++s->count < (s->heat >= 4 ? 32u : 64u)) return 0;
    s->count = 0;
    return s->heat >= 4 ? 2 : 1;
}

/* Called only after the requested 50us pause. Return 1 when entering cooldown. */
static inline int fex_yield_adaptive_complete(struct fex_yield_adaptive *s,
                                            uint64_t begin, uint64_t end)
{
    s->last = end;
    if (end < begin || end - begin > 2000) {
        s->count = s->heat = 0;
        s->cooling = 1;
        s->cool_since = end;
        return 1;
    }
    /* Only inexpensive, consecutive pauses earn the shorter polling burst. */
    if (end - begin > 1000) s->heat = 0;
    else if (s->heat < 4) ++s->heat;
    return 0;
}
#endif
