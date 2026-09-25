// SPDX-License-Identifier: MIT
#include "horizon_host.h"
#include <FEXCore/Config/Config.h>

extern "C" void PES13FexApplyPerformanceProfile(void) {
    const unsigned profile = PES13FexPerformanceProfile();
    using namespace FEXCore::Config;
    // Project profiles, not names supplied by upstream FEX. Apply before
    // constructing the context so these settings govern every compiled block.
    Set(CONFIG_X87REDUCEDPRECISION, profile ? "1" : "0");
    Set(CONFIG_TSOENABLED, profile == 2 ? "0" : "1");
    // Team selection crosses producer/consumer worker queues. Fast retains
    // x86 ordering for scalar, SIMD and string accesses; only the explicitly
    // experimental Fastest profile relaxes it. Keep the faster x87 format.
    Set(CONFIG_VECTORTSOENABLED, profile == 2 ? "0" : "1");
    Set(CONFIG_MEMCPYSETTSOENABLED, profile == 2 ? "0" : "1");
    Set(CONFIG_HALFBARRIERTSOENABLED, "1");
    Set(CONFIG_MULTIBLOCK, "1");
    Set(CONFIG_MAXINST, "5000");
    // Do not disable code invalidation, LOCK semantics, or enable CPU
    // instructions absent on Cortex-A57 just to label a profile "fast".
    Set(CONFIG_SMCCHECKS, "1"); // CONFIG_SMC_MTRACK
    static_assert(CONFIG_SMC_MTRACK == 1);
    PES13FexLog(profile == 2
        ? "[FEX3-PRESET] fastest x87=64 scalar_tso=0 vector_tso=0 memcpy_tso=0 multiblock=1 maxinst=5000 smc=mtrack"
        : profile == 1
        ? "[FEX3-PRESET] fast x87=64 scalar_tso=1 vector_tso=1 memcpy_tso=1 multiblock=1 maxinst=5000 smc=mtrack"
        : "[FEX3-PRESET] control x87=80 scalar_tso=1 vector_tso=1 memcpy_tso=1 multiblock=1 maxinst=5000 smc=mtrack");
}
