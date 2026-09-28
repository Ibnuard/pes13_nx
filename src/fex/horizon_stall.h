/* SPDX-License-Identifier: MIT */
#ifndef PES13_FEX_HORIZON_STALL_H
#define PES13_FEX_HORIZON_STALL_H
#include <stdint.h>

/* Called once per five-second heartbeat, not from rendered frames. */
struct pes13_fex_stall_gate {
    uint32_t presents, last_progress, last_capture, captures;
};
static inline int pes13_fex_stall_due(struct pes13_fex_stall_gate *gate,
                                     uint32_t presents, uint32_t seconds)
{
    if (presents != gate->presents) {
        gate->presents = presents;
        gate->last_progress = seconds;
        return 0;
    }
    if (presents < 100 || seconds - gate->last_progress < 10 || gate->captures >= 3 ||
        (gate->captures && seconds - gate->last_capture < 5)) return 0;
    gate->last_capture = seconds;
    ++gate->captures;
    return 1;
}

/* Pinned FEX layout, checked by static_assert in the actual FEX build. The
 * observer reads only while the owning kernel thread is paused. No FEX locks,
 * callbacks, allocation, or logging are allowed during that pause. */
#define PES13_FEX_FRAME_BLOCK_OFFSET 0
#define PES13_FEX_FRAME_RIP_OFFSET 24
struct pes13_fex_observed_tail {
    uint64_t size, rip, guest_size;
    uint32_t rip_entries, rip_offset, spinlock;
    uint8_t single, pad[3];
};
#endif
