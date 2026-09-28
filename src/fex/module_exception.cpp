// SPDX-License-Identifier: MIT
#include <atomic>
#include "horizon_host.h"

namespace {
std::atomic<uint32_t> Sequence {0};
constexpr uint32_t MaxTraces = 12;

char *Text(char *out, const char *value) {
    while (*value) *out++ = *value++;
    return out;
}
char *Hex(char *out, uint64_t value) {
    out = Text(out, "0x");
    for (int shift = 60; shift >= 0; shift -= 4)
        *out++ = "0123456789abcdef"[(value >> shift) & 15];
    return out;
}
}

extern "C" uint32_t PES13FexBeginGuestFaultTrace(uint64_t tid, uint64_t host_pc, uint64_t address) {
    // Saturate rather than wrap after a long-running application's faults.
    uint32_t index = Sequence.load(std::memory_order_relaxed);
    do {
        if (index >= MaxTraces) return 0;
    } while (!Sequence.compare_exchange_weak(index, index+1, std::memory_order_relaxed));
    char message[208];
    char *out = Hex(Text(message, "[FEX3-GEX] ticket="), index+1);
    out = Hex(Text(out, " tid="), tid);
    out = Text(out, " stage=candidate");
    out = Hex(Text(out, " host_pc="), host_pc);
    out = Hex(Text(out, " address="), address);
    *out = 0;
    PES13FexLog(message);
    return index+1;
}

extern "C" void PES13FexTraceGuestFault(uint32_t ticket, const char *stage, uint64_t pc, uint64_t value) {
    if (!ticket || ticket > MaxTraces || !stage) return;
    char message[208];
    char *out = Hex(Text(message, "[FEX3-GEX] ticket="), ticket);
    out = Text(Text(out, " stage="), stage); // Internal fixed stage labels only.
    out = Hex(Text(out, " pc="), pc);
    out = Hex(Text(out, " value="), value);
    *out = 0;
    PES13FexLog(message);
}
