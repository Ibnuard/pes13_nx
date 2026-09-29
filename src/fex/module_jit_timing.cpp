// SPDX-License-Identifier: MIT
#include "horizon_host.h"
#include "horizon_counter.h"
#include "horizon_jit_timing.h"
#include "horizon_compile_trace.h"
#include <atomic>
#include <cstdlib>
#include <windows.h>
#include <winternl.h>

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

// Diagnostic-only, enabled once from the launcher environment. No allocations,
// host callbacks or formatting in ShortEnd (called inside compilation scopes).
bool ShortEnabled{};
struct ShortSlow { uint64_t begin{}, end{}; };
struct ShortWindow {
    uint64_t begin{}, end{}, count{}, ticks{}, peak{}, slow_dropped{};
    unsigned tid{}, slow_count{};
    ShortSlow slow[4]{};
};
struct ShortSlot {
    std::atomic_flag busy = ATOMIC_FLAG_INIT;
    ShortWindow window{};
};
ShortSlot ShortSlots[128];
std::atomic<uint64_t> ShortDropped{0};
unsigned ShortTid() {
    auto *teb = reinterpret_cast<__TEB *>(NtCurrentTeb());
    return teb ? static_cast<unsigned>(reinterpret_cast<uintptr_t>(teb->ClientId.UniqueThread)) : 0;
}
void ShortEnd(uint64_t begin, uint64_t end) {
    if (!ShortEnabled) return;
    const auto tid = ShortTid();
    auto &slot = ShortSlots[(tid >> 2) % 128];
    if (slot.busy.test_and_set(std::memory_order_acquire)) {
        ShortDropped.fetch_add(1, std::memory_order_relaxed); return;
    }
    auto &w = slot.window;
    if (w.count && w.tid != tid) ShortDropped.fetch_add(1, std::memory_order_relaxed);
    else {
        if (!w.count) { w.tid = tid; w.begin = begin; }
        if (begin < w.begin) w.begin = begin;
        if (end > w.end) w.end = end;
        ++w.count; w.ticks += end - begin;
        if (end - begin > w.peak) w.peak = end - begin;
        if (end - begin >= Frequency / 50) {
            if (w.slow_count < 4) w.slow[w.slow_count++] = {begin, end};
            else ++w.slow_dropped;
        }
    }
    slot.busy.clear(std::memory_order_release);
}
void ShortReport(uint64_t now) {
    if (!ShortEnabled) return;
    // Caller is ReportScope, after compilation locks unwind. Native bridge
    // consumes these prefixes through a bounded queue, even when disabled/full.
    for (auto &slot : ShortSlots) {
        if (slot.busy.test_and_set(std::memory_order_acquire)) continue;
        const auto w = slot.window;
        slot.window = {};
        slot.busy.clear(std::memory_order_release);
        if (!w.count) continue;
        char line[384], *p = Text(line, "[FEX3-JIT-THREAD] tid=");
        p = Number(p, w.tid);
        p = Number(Text(p, " begin_tick="), w.begin);
        p = Number(Text(p, " end_tick="), w.end);
        p = Number(Text(p, " report_tick="), now);
        p = Number(Text(p, " calls="), w.count);
        p = Number(Text(p, " total_us="), Micros(w.ticks));
        p = Number(Text(p, " peak_us="), Micros(w.peak));
        p = Number(Text(p, " slow_dropped="), w.slow_dropped);
        p = Number(Text(p, " slot_dropped_cumulative="), ShortDropped.load(std::memory_order_relaxed));
        *p = 0; PES13FexLog(line);
        for (unsigned i = 0; i < w.slow_count; ++i) {
            p = Number(Text(line, "[FEX3-JIT-SLOW] tid="), w.tid);
            p = Number(Text(p, " begin_tick="), w.slow[i].begin);
            p = Number(Text(p, " end_tick="), w.slow[i].end);
            p = Number(Text(p, " wall_us="), Micros(w.slow[i].end - w.slow[i].begin));
            *p = 0; PES13FexLog(line);
        }
    }
}
}

extern "C" void PES13FexJitTimingInit(void) {
    PES13FexCompileTraceInit();
    Frequency = pes13_fex_counter_frequency();
    Origin = pes13_fex_counter();
    LastReport.store(Origin, std::memory_order_relaxed);
    const char *trace = getenv("FEXTENDO_TRACE");
    ShortEnabled = trace && trace[0] == '1' && trace[1] == 0;
    if (ShortEnabled) {
        char line[192], *p = Number(Text(line, "[FEX3-JIT-CLOCK] origin_tick="), Origin);
        p = Number(Text(p, " frequency="), Frequency);
        p = Text(p, " stage=compile_code windows=5s threshold_us=20000 slots=128 slow_per_slot=4");
        *p = 0; PES13FexLog(line);
    }
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
    if (stage == 1) ShortEnd(begin, end);
}

extern "C" void PES13FexJitReport(void) {
    if (!Frequency) return;
    const auto now = pes13_fex_counter();
    auto old = LastReport.load(std::memory_order_relaxed);
    if (now < old || now - old < Frequency * 5 ||
        !LastReport.compare_exchange_strong(old, now, std::memory_order_relaxed)) return;
    ShortReport(now);
    PES13FexCompileTraceReport(now);
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
