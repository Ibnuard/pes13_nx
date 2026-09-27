/* SPDX-License-Identifier: MIT. Completed JIT CPU calls, not simulation FPS. */
#pragma once
#include <stdint.h>

extern "C" uint64_t PES13FexJitBegin(void);
extern "C" void PES13FexJitEnd(unsigned stage, uint64_t begin);
extern "C" void PES13FexJitReport(void);
extern "C" void PES13FexJitTimingInit(void);

struct PES13FexJitScope {
    unsigned stage;
    uint64_t begin;
    explicit PES13FexJitScope(unsigned s) : stage{s}, begin{PES13FexJitBegin()} {}
    ~PES13FexJitScope() { PES13FexJitEnd(stage, begin); }
};

/* Declare before the compile scope so reporting occurs after its locks unwind. */
struct PES13FexJitReportScope {
    ~PES13FexJitReportScope() { PES13FexJitReport(); }
};
