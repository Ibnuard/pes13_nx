// SPDX-License-Identifier: MIT
#include "horizon_host.h"
#include "horizon_counter.h"
#include "horizon_jit_timing.h"
#include <atomic>

namespace {
struct Metric {
    std::atomic<uint64_t> count{0}, ticks{0}, peak{0}, slow20{0}, slow50{0};
};
Metric Stats[3];
uint64_t Frequency{}, Origin{};
std::atomic<uint64_t> LastReport{0};
char *Text(char *p, const char *s) { while (*s) *p++ = *s++; return p; }
char *Number(char *p, uint64_t n) {
    char buf[24]; unsigned size = 0;
    do { buf[size++] = '0' + n % 10; n /= 10; } while (n);
    while (size) *p++ = buf[--size];
    return p;
}
uint64_t Micros(uint64_t ticks) {
    return ticks / Frequency * 1000000 + ticks % Frequency * 1000000 / Frequency;
}
}

extern "C" void PES13FexJitTimingInit(void) {
    Frequency = pes13_fex_counter_frequency();
    Origin = pes13_fex_counter();
    LastReport.store(Origin, std::memory_order_relaxed);
    PES13FexLog("[FEX3-JIT] v1 cumulative completed-call timing; nested stages overlap; reports after compilation locks unwind");
}

extern "C" uint64_t PES13FexJitBegin(void) { return pes13_fex_counter(); }

extern "C" void PES13FexJitEnd(unsigned stage, uint64_t begin) {
    const auto end = pes13_fex_counter();
    if (stage >= 3 || !Frequency || end < begin) return;
    const auto elapsed = end - begin;
    auto &s = Stats[stage];
    s.count.fetch_add(1, std::memory_order_relaxed);
    s.ticks.fetch_add(elapsed, std::memory_order_relaxed);
    auto peak = s.peak.load(std::memory_order_relaxed);
    while (peak < elapsed && !s.peak.compare_exchange_weak(peak, elapsed, std::memory_order_relaxed)) {}
    if (elapsed > Frequency / 50) s.slow20.fetch_add(1, std::memory_order_relaxed);
    if (elapsed > Frequency / 20) s.slow50.fetch_add(1, std::memory_order_relaxed);
}

extern "C" void PES13FexJitReport(void) {
    if (!Frequency) return;
    const auto now = pes13_fex_counter();
    auto old = LastReport.load(std::memory_order_relaxed);
    if (now < old || now - old < Frequency * 5 ||
        !LastReport.compare_exchange_strong(old, now, std::memory_order_relaxed)) return;
    static const char *names[] = {"dispatch_compile", "compile_code", "invalidate"};
    for (unsigned stage = 0; stage < 3; ++stage) {
        const auto &s = Stats[stage];
        char line[320], *p = Text(line, "[FEX3-JIT] phase=");
        p = Text(p, names[stage]);
        p = Number(Text(p, " uptime_ms="), Micros(now - Origin) / 1000);
        p = Number(Text(p, " calls="), s.count.load(std::memory_order_relaxed));
        p = Number(Text(p, " total_us="), Micros(s.ticks.load(std::memory_order_relaxed)));
        p = Number(Text(p, " peak_us="), Micros(s.peak.load(std::memory_order_relaxed)));
        p = Number(Text(p, " over20ms="), s.slow20.load(std::memory_order_relaxed));
        p = Number(Text(p, " over50ms="), s.slow50.load(std::memory_order_relaxed));
        *p = 0;
        PES13FexLog(line);
    }
}
