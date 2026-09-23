/* Extend the tested PERF21 environment with Box64's float-when-possible
 * x87 policy. Selection remains under the translator mutex; no live global
 * mutation and no helper added to executed guest code. */
#ifndef PES13_PERF22_H
#define PES13_PERF22_H
static int pes22_mode;
static box64env_t pes22_env;
static unsigned int pes22_active, pes22_selected, pes22_completed;

static box64env_t *pes22_select(uintptr_t addr)
{
    box64env_t *baseline = pes21_select(addr);
    if (!pes22_mode || baseline != &pes21_env) return baseline;
    if (!__atomic_load_n(&pes22_active, __ATOMIC_RELAXED)) {
        pes22_env = *baseline;
        pes22_env.dynarec_x87double = 0;
        pes22_env.is_dynarec_x87double_overridden = 1;
        pes22_env.is_any_overridden = 1;
        __atomic_store_n(&pes22_active, 1, __ATOMIC_RELEASE);
    }
    __atomic_add_fetch(&pes22_selected, 1, __ATOMIC_RELAXED);
    return &pes22_env;
}

uintptr_t wine_nx_perf22_block_end(uintptr_t start, uintptr_t end, const void *env)
{
    return wine_nx_perf21_block_end(start, end, env == &pes22_env ? &pes21_env : env);
}

void wine_nx_perf22_completed(void *opaque, const void *env)
{
    if (env == &pes22_env) {
        __atomic_add_fetch(&pes22_completed, 1, __ATOMIC_RELAXED);
        /* Preserve PERF21's aggregate completion counter. */
        __atomic_add_fetch(&pes21_completed, 1, __ATOMIC_RELAXED);
        wine_nx_perf20_capture(opaque);
    } else {
        wine_nx_perf21_completed(opaque, env);
    }
}

void wine_nx_perf22_report(void)
{
    char line[320];
    unsigned int active = __atomic_load_n(&pes22_active, __ATOMIC_ACQUIRE);
    unsigned int fast = __atomic_load_n(&pes21_active, __ATOMIC_ACQUIRE);
    const box64env_t *env = active ? &pes22_env : fast ? &pes21_env : &box64env;
    snprintf(line, sizeof(line),
        "[PERF22] enabled=%d active=%u selected=%u completed=%u game_X87DOUBLE=%d baseline_X87DOUBLE=%d FASTROUND=%d SAFEFLAGS=%d FASTNAN=%d STRONGMEM=%d BIGBLOCK=%d CALLRET=%d",
        __atomic_load_n(&pes22_mode, __ATOMIC_ACQUIRE), active,
        __atomic_load_n(&pes22_selected, __ATOMIC_RELAXED),
        __atomic_load_n(&pes22_completed, __ATOMIC_RELAXED),
        env->dynarec_x87double, box64env.dynarec_x87double,
        env->dynarec_fastround, env->dynarec_safeflags, env->dynarec_fastnan,
        env->dynarec_strongmem, env->dynarec_bigblock, env->dynarec_callret);
    if (&wine_nx_runtime_trace) wine_nx_runtime_trace(line);
}
#endif
