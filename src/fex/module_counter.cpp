// SPDX-License-Identifier: MIT
#include "horizon_host.h"
#include "horizon_counter.h"

extern "C" void PES13FexCounterPreflight(void) {
    PES13FexLog("[FEX2-TIMER] v3 physical counter CNTPCT_EL0; checking before CRT");
    const uint64_t frequency = pes13_fex_counter_frequency();
    const uint64_t first = pes13_fex_counter();
    uint64_t previous = first;
    for (unsigned i = 0; i < 64; ++i) {
        const uint64_t now = pes13_fex_counter();
        if (now < previous) {
            PES13FexLog("[FEX2-TIMER] STOP counter moved backwards");
            __builtin_trap();
        }
        previous = now;
    }
    if (!frequency || previous == first) {
        PES13FexLog("[FEX2-TIMER] STOP frequency is zero or counter did not advance");
        __builtin_trap();
    }
    // No CRT formatting during a pre-CRT check.
    char message[] = "[FEX2-TIMER] PASS physical counter frequency=0x0000000000000000";
    constexpr unsigned digits = sizeof(message) - 1 - 16;
    for (unsigned i = 0; i < 16; ++i)
        message[digits+i] = "0123456789abcdef"[(frequency >> ((15-i)*4)) & 15];
    PES13FexLog(message);
}
