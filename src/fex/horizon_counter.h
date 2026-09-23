/* SPDX-License-Identifier: MIT
 * Horizon exposes CNTPCT_EL0 to applications (the libnx system tick).
 * CNTVCT_EL0 traps on the tested 32-bit/no-alias forwarder configuration.
 * Both the host and emitted guest counter must use this clock domain.
 */
#ifndef PES13_FEX_HORIZON_COUNTER_H
#define PES13_FEX_HORIZON_COUNTER_H
#include <stdint.h>

static inline uint64_t pes13_fex_counter(void) {
    uint64_t ticks;
    __asm__ volatile("isb; mrs %0, cntpct_el0" : "=r"(ticks) : : "memory");
    return ticks;
}

static inline uint64_t pes13_fex_counter_frequency(void) {
    uint64_t frequency;
    __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(frequency));
    return frequency;
}
#endif
