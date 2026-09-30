// SPDX-License-Identifier: MIT
#include "horizon_host.h"
#include <FEXCore/Config/Config.h>

extern "C" void PES13FexApplyPerformanceProfile(void) {
    const unsigned profile = PES13FexPerformanceProfile();
    const bool fastest = profile == PES13_FEX_FASTEST;
    const bool relaxed_vectors = fastest || profile == PES13_FEX_FAST_VECTOR;
    using namespace FEXCore::Config;
    // Project profiles, not names supplied by upstream FEX. Apply before
    // constructing the context so these settings govern every compiled block.
    Set(CONFIG_X87REDUCEDPRECISION, profile ? "1" : "0");
    Set(CONFIG_TSOENABLED, fastest ? "0" : "1");
    // Fast stays the normal-speed control. Fast-vector changes only vector
    // ordering: avoid SIMD DMBs while retaining scalar and REP MOVS/STOS TSO.
    // This remains a compatibility tradeoff if guest threads share vector data.
    Set(CONFIG_VECTORTSOENABLED, relaxed_vectors ? "0" : "1");
    Set(CONFIG_MEMCPYSETTSOENABLED, fastest ? "0" : "1");
    Set(CONFIG_HALFBARRIERTSOENABLED, "1");
    Set(CONFIG_MULTIBLOCK, "1");
    PES13FexLog("[FEX3-DECODE] v1 inline worklists=64; ordered-tree overflow; no persistent cache required");
    // The launcher can select a latency experiment through FEX's existing
    // environment config. Keep the previous cap for every other value.
    FEX_CONFIG_OPT(RequestedMaxInst, MAXINST);
    const unsigned requested = RequestedMaxInst();
    const unsigned maxinst = profile && (requested == 128 || requested == 500) ? requested : 5000;
    Set(CONFIG_MAXINST, maxinst == 128 ? "128" : maxinst == 500 ? "500" : "5000");
    PES13FexLog(maxinst == 128
        ? "[FEX3-JIT-CONFIG] maxinst=128 multiblock=1; cold-start candidate"
        : maxinst == 500
        ? "[FEX3-JIT-CONFIG] maxinst=500 multiblock=1; latency candidate"
        : "[FEX3-JIT-CONFIG] maxinst=5000 multiblock=1; control");
    // Do not disable code invalidation, LOCK semantics, or enable CPU
    // instructions absent on Cortex-A57 just to label a profile "fast".
    Set(CONFIG_SMCCHECKS, "1"); // CONFIG_SMC_MTRACK
    static_assert(CONFIG_SMC_MTRACK == 1);
    PES13FexLog(fastest
        ? "[FEX3-PRESET] fastest x87=64 scalar_tso=0 vector_tso=0 memcpy_tso=0 multiblock=1 smc=mtrack"
        : profile == PES13_FEX_FAST_VECTOR
        ? "[FEX3-PRESET] fast-vector x87=64 scalar_tso=1 vector_tso=0 memcpy_tso=1 multiblock=1 smc=mtrack"
        : profile == PES13_FEX_FAST
        ? "[FEX3-PRESET] fast x87=64 scalar_tso=1 vector_tso=1 memcpy_tso=1 multiblock=1 smc=mtrack"
        : "[FEX3-PRESET] control x87=80 scalar_tso=1 vector_tso=1 memcpy_tso=1 multiblock=1 maxinst=5000 smc=mtrack");
}
