// SPDX-License-Identifier: MIT
#pragma once
#include <stdint.h>

extern "C" void PES13FexCompileTraceInit(void);
extern "C" void PES13FexCompileTraceReport(uint64_t now);
extern "C" uint64_t PES13FexCompileTraceClock(void);

struct PES13FexCompileTrace {
    uint64_t rip, begin, elapsed[4]{}, instructions{}, host_bytes{};
    unsigned outcome{}; // 0 empty/failure, 1 code generated, 2 another compiler won
    explicit PES13FexCompileTrace(uint64_t address);
    ~PES13FexCompileTrace();
    uint64_t *Phases() { return begin ? elapsed : nullptr; }
};

struct PES13FexCompilePhase {
    uint64_t *ticks, begin;
    explicit PES13FexCompilePhase(uint64_t *phases, unsigned phase)
        : ticks{phases ? phases + phase : nullptr}, begin{ticks ? PES13FexCompileTraceClock() : 0} {}
    ~PES13FexCompilePhase() {
        if (ticks) { const auto end = PES13FexCompileTraceClock(); if (end >= begin) *ticks += end - begin; }
    }
};
