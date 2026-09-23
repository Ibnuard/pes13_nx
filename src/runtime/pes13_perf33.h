/* Include after PERF25. Existing translator mutex serializes all selection
 * and completion. No runtime branch or helper added to executed guest code. */
#ifndef PES13_PERF33_H
#define PES13_PERF33_H
#include "pes13_perf33_policy.h"
static int pes33_mode;
static box64env_t pes33_env;
static unsigned int pes33_ready, pes33_selected, pes33_completed_count;
static unsigned long long pes33_guest_bytes, pes33_native_bytes;
static unsigned int pes33_max_guest, pes33_max_native;

static box64env_t *pes33_select(uintptr_t address, box64env_t *base)
{
    /* Only the established FASTROUND=1, X87DOUBLE=1 environment is eligible.
     * A different float-math experiment or the boot/global environment falls
     * back unchanged. Older blocks keep their originally selected env. */
    if (!pes33_mode || base!=&pes21_env || !pes17_check_image() ||
        !__atomic_load_n(&wine_nx_vk_successful_presents,__ATOMIC_ACQUIRE) ||
        !pes33_limit(address)) return base;
    if (!__atomic_load_n(&pes33_ready,__ATOMIC_RELAXED)) {
        pes33_env=*base;
        /* PERF33 fastmath candidate: only newly translated post-present game
         * blocks use the Box64 fastest memory/NaN policy. Startup, DLLs and
         * the parent environment remain PERF25-compatible. */
        pes33_env.dynarec_fastnan=1;
        pes33_env.is_dynarec_fastnan_overridden=1;
        pes33_env.dynarec_strongmem=0;
        pes33_env.is_dynarec_strongmem_overridden=1;
        pes33_env.dynarec_forward=1024;
        pes33_env.is_dynarec_forward_overridden=1;
        pes33_env.dynarec_bigblock=3;
        pes33_env.is_dynarec_bigblock_overridden=1;
        pes33_env.is_any_overridden=1;
        __atomic_store_n(&pes33_ready,1,__ATOMIC_RELEASE);
    }
    __atomic_add_fetch(&pes33_selected,1,__ATOMIC_RELAXED);
    return &pes33_env;
}

const void *wine_nx_perf33_base(const void *env)
{
    return env==&pes33_env ? &pes21_env : env;
}

uintptr_t wine_nx_perf33_block_end(uintptr_t start, uintptr_t end, const void *env)
{
    end=wine_nx_perf22_block_end(start,end,wine_nx_perf33_base(env));
    uintptr_t limit=pes33_limit(start);
    return env==&pes33_env && limit && end>=limit ? limit-1 : end;
}

void wine_nx_perf33_completed(void *opaque, const void *env)
{
    const dynablock_t *db=opaque;
    if (env==&pes33_env) {
        __atomic_add_fetch(&pes33_completed_count,1,__ATOMIC_RELAXED);
        __atomic_add_fetch(&pes33_guest_bytes,db->x64_size,__ATOMIC_RELAXED);
        __atomic_add_fetch(&pes33_native_bytes,db->native_size,__ATOMIC_RELAXED);
        if (db->x64_size>pes33_max_guest) __atomic_store_n(&pes33_max_guest,db->x64_size,__ATOMIC_RELAXED);
        if (db->native_size>pes33_max_native) __atomic_store_n(&pes33_max_native,db->native_size,__ATOMIC_RELAXED);
    }
    wine_nx_perf25_completed(opaque,wine_nx_perf33_base(env));
}

void wine_nx_perf33_report(void)
{
    char line[320];
    snprintf(line,sizeof(line),
        "[PERF33] base=PERF25 CALLRET=0 worker_blocks=%d ready=%u selected=%u completed=%u guest_bytes=%llu native_bytes=%llu max_guest=%u max_native=%u scoped_BIGBLOCK=3 FASTNAN=1 STRONGMEM=0 FORWARD=1024 baseline_BIGBLOCK=%d; compilation counts, not executions",
        __atomic_load_n(&pes33_mode,__ATOMIC_RELAXED),__atomic_load_n(&pes33_ready,__ATOMIC_ACQUIRE),
        __atomic_load_n(&pes33_selected,__ATOMIC_RELAXED),__atomic_load_n(&pes33_completed_count,__ATOMIC_RELAXED),
        __atomic_load_n(&pes33_guest_bytes,__ATOMIC_RELAXED),__atomic_load_n(&pes33_native_bytes,__ATOMIC_RELAXED),
        __atomic_load_n(&pes33_max_guest,__ATOMIC_RELAXED),__atomic_load_n(&pes33_max_native,__ATOMIC_RELAXED),
        box64env.dynarec_bigblock);
    if (&wine_nx_runtime_trace) wine_nx_runtime_trace(line);
}
#endif
