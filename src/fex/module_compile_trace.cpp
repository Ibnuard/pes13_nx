// SPDX-License-Identifier: MIT
// Completed compile work by guest entry address. Fixed memory, bounded probes,
// try-lock producers, no allocation or I/O while compilation locks are held.
#include "horizon_compile_trace.h"
#include "horizon_counter.h"
#include "horizon_host.h"
#include <atomic>
#include <cstdlib>

namespace FexCompileTraceDetail {
constexpr unsigned Slots = 2048, Probes = 16, Top = 12;
struct Row {
    uint64_t rip{}, calls{}, total{}, peak{}, phases[4]{}, first{}, last{};
    uint64_t instructions{}, bytes{}, generated{}, raced{}, empty{};
};
Row Rows[Slots], Totals;
std::atomic_flag Busy = ATOMIC_FLAG_INIT;
std::atomic<uint64_t> Lost{0};
bool Enabled{};
uint64_t Frequency{};
char *Text(char *p, const char *s) { while (*s) *p++ = *s++; return p; }
char *Num(char *p, uint64_t n) {
    char b[24]; unsigned i=0;
    do { b[i++] = '0' + n % 10; n /= 10; } while (n);
    while (i) *p++ = b[--i];
    return p;
}
uint64_t Us(uint64_t n) { return n / Frequency * 1000000 + n % Frequency * 1000000 / Frequency; }
void Add(Row &r, const PES13FexCompileTrace &t, uint64_t end) {
    if (!r.calls) { r.rip = t.rip; r.first = t.begin; }
    ++r.calls; if (end > r.last) r.last = end;
    const auto duration = end - t.begin;
    r.total += duration;
    if (r.peak < duration) r.peak = duration;
    if (t.begin < r.first) r.first = t.begin;
    for (unsigned i=0; i<4; ++i) r.phases[i] += t.elapsed[i];
    r.instructions += t.instructions; r.bytes += t.host_bytes;
    r.generated += t.outcome == 1; r.raced += t.outcome == 2; r.empty += t.outcome == 0;
}
void Emit(const char *prefix, const Row &r, uint64_t now, uint64_t lost) {
    char line[768], *p=Text(line,prefix);
    p=Num(Text(p," rip="),r.rip);
    p=Num(Text(p," begin_tick="),r.first); p=Num(Text(p," end_tick="),r.last);
    p=Num(Text(p," report_tick="),now); p=Num(Text(p," calls="),r.calls);
    p=Num(Text(p," total_us="),Us(r.total)); p=Num(Text(p," peak_us="),Us(r.peak));
    p=Num(Text(p," decode_us="),Us(r.phases[0])); p=Num(Text(p," passes_us="),Us(r.phases[1]));
    p=Num(Text(p," frontend_us="),Us(r.phases[2])); p=Num(Text(p," backend_us="),Us(r.phases[3]));
    p=Num(Text(p," generated="),r.generated); p=Num(Text(p," raced="),r.raced);
    p=Num(Text(p," empty="),r.empty); p=Num(Text(p," guest_inst="),r.instructions);
    p=Num(Text(p," host_bytes="),r.bytes); p=Num(Text(p," lost="),lost);
    *p=0; PES13FexLog(line);
}
}

extern "C" void PES13FexCompileTraceInit(void) {
    using namespace FexCompileTraceDetail;
    const char *s=getenv("FEXTENDO_TRACE");
    Enabled=s && s[0]=='1' && !s[1];
    Frequency=pes13_fex_counter_frequency();
    if (!Frequency) Enabled=false;
}
extern "C" uint64_t PES13FexCompileTraceClock(void) { return FexCompileTraceDetail::Enabled ? pes13_fex_counter() : 0; }
PES13FexCompileTrace::PES13FexCompileTrace(uint64_t address) : rip{address}, begin{PES13FexCompileTraceClock()} {}
PES13FexCompileTrace::~PES13FexCompileTrace() {
    using namespace FexCompileTraceDetail;
    if (!begin) return;
    const auto end=pes13_fex_counter();
    if (end < begin) return;
    if (Busy.test_and_set(std::memory_order_acquire)) { Lost.fetch_add(1,std::memory_order_relaxed); return; }
    Add(Totals,*this,end);
    const unsigned key=((rip >> 2) ^ (rip >> 16)) & (Slots-1);
    bool found=false;
    for (unsigned i=0;i<Probes;++i) {
        auto &r=Rows[(key+i)&(Slots-1)];
        if (!r.calls || r.rip==rip) { Add(r,*this,end); found=true; break; }
    }
    if (!found) Lost.fetch_add(1,std::memory_order_relaxed);
    Busy.clear(std::memory_order_release);
}
extern "C" void PES13FexCompileTraceReport(uint64_t now) {
    using namespace FexCompileTraceDetail;
    if (!Enabled || Busy.test_and_set(std::memory_order_acquire)) return;
    Row top[Top]{}, total=Totals;
    // Reporting is outside compile locks. Producers never wait for this scan.
    for (auto &r:Rows) {
        if (!r.calls) continue;
        for (unsigned i=0;i<Top;++i) if (r.total>top[i].total) {
            for (unsigned j=Top-1;j>i;--j) top[j]=top[j-1];
            top[i]=r; break;
        }
        r={};
    }
    Totals={};
    const auto lost=Lost.exchange(0,std::memory_order_relaxed);
    Busy.clear(std::memory_order_release);
    if (total.calls || lost) Emit("[FEX3-COMPILE]",total,now,lost);
    for (const auto &r:top) if (r.calls) Emit("[FEX3-BLOCK]",r,now,0);
}
