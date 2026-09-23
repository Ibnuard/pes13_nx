/* Include after PERF25. Existing translator mutex serializes all selection
 * and completion. No runtime branch or helper added to executed guest code. */
#ifndef PES13_PERF32_H
#define PES13_PERF32_H
#include "pes13_perf32_policy.h"
static int pes32_mode;
static box64env_t pes32_env;
static unsigned int pes32_ready, pes32_selected, pes32_completed_count;
static unsigned long long pes32_guest_bytes, pes32_native_bytes;
static unsigned int pes32_max_guest, pes32_max_native;

static box64env_t *pes32_select(uintptr_t address, box64env_t *base)
{
    /* Only the established FASTROUND=1, X87DOUBLE=1 environment is eligible.
     * A different float-math experiment or the boot/global environment falls
     * back unchanged. Older blocks keep their originally selected env. */
    if (!pes32_mode || base!=&pes21_env || !pes17_check_image() ||
        !__atomic_load_n(&wine_nx_vk_successful_presents,__ATOMIC_ACQUIRE) ||
        !pes32_limit(address)) return base;
    if (!__atomic_load_n(&pes32_ready,__ATOMIC_RELAXED)) {
        pes32_env=*base;
        pes32_env.dynarec_bigblock=3;
        pes32_env.is_dynarec_bigblock_overridden=1;
        pes32_env.is_any_overridden=1;
        __atomic_store_n(&pes32_ready,1,__ATOMIC_RELEASE);
    }
    __atomic_add_fetch(&pes32_selected,1,__ATOMIC_RELAXED);
    return &pes32_env;
}

const void *wine_nx_perf32_base(const void *env)
{
    return env==&pes32_env ? &pes21_env : env;
}

uintptr_t wine_nx_perf32_block_end(uintptr_t start, uintptr_t end, const void *env)
{
    end=wine_nx_perf22_block_end(start,end,wine_nx_perf32_base(env));
    uintptr_t limit=pes32_limit(start);
    return env==&pes32_env && limit && end>=limit ? limit-1 : end;
}

void wine_nx_perf32_completed(void *opaque, const void *env)
{
    const dynablock_t *db=opaque;
    if (env==&pes32_env) {
        __atomic_add_fetch(&pes32_completed_count,1,__ATOMIC_RELAXED);
        __atomic_add_fetch(&pes32_guest_bytes,db->x64_size,__ATOMIC_RELAXED);
        __atomic_add_fetch(&pes32_native_bytes,db->native_size,__ATOMIC_RELAXED);
        if (db->x64_size>pes32_max_guest) __atomic_store_n(&pes32_max_guest,db->x64_size,__ATOMIC_RELAXED);
        if (db->native_size>pes32_max_native) __atomic_store_n(&pes32_max_native,db->native_size,__ATOMIC_RELAXED);
    }
    wine_nx_perf25_completed(opaque,wine_nx_perf32_base(env));
}

void wine_nx_perf32_report(void)
{
    char line[320];
    snprintf(line,sizeof(line),
        "[PERF32] base=PERF25 CALLRET=0 worker_blocks=%d ready=%u selected=%u completed=%u guest_bytes=%llu native_bytes=%llu max_guest=%u max_native=%u scoped_BIGBLOCK=3 baseline_BIGBLOCK=%d; compilation counts, not executions",
        __atomic_load_n(&pes32_mode,__ATOMIC_RELAXED),__atomic_load_n(&pes32_ready,__ATOMIC_ACQUIRE),
        __atomic_load_n(&pes32_selected,__ATOMIC_RELAXED),__atomic_load_n(&pes32_completed_count,__ATOMIC_RELAXED),
        __atomic_load_n(&pes32_guest_bytes,__ATOMIC_RELAXED),__atomic_load_n(&pes32_native_bytes,__ATOMIC_RELAXED),
        __atomic_load_n(&pes32_max_guest,__ATOMIC_RELAXED),__atomic_load_n(&pes32_max_native,__ATOMIC_RELAXED),
        box64env.dynarec_bigblock);
    if (&wine_nx_runtime_trace) wine_nx_runtime_trace(line);
}
#endif
