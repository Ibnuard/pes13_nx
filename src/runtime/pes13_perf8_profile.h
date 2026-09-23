/* Experimental per-block policy. Included after Box64's env declarations.
 * GetCurEnvByAddr runs under Box64's translator mutex. Never mutate the
 * process-wide environment while other threads execute translated code. */
#ifndef PES13_PERF8_PROFILE_H
#define PES13_PERF8_PROFILE_H

extern unsigned int wine_nx_vk_successful_presents;
static box64env_t pes13_perf8_game_env;
static unsigned int pes13_perf8_active, pes13_perf8_builds;
static int pes13_perf8_enabled = 1;

static box64env_t *pes13_perf8_select_env(uintptr_t addr)
{
    (void)addr;
    if (!pes13_perf8_enabled ||
        !__atomic_load_n(&wine_nx_vk_successful_presents, __ATOMIC_ACQUIRE))
        return &box64env;
    if (!__atomic_load_n(&pes13_perf8_active, __ATOMIC_RELAXED))
    {
        pes13_perf8_game_env = box64env;
        pes13_perf8_game_env.dynarec_bigblock = 1;
        pes13_perf8_game_env.is_dynarec_bigblock_overridden = 1;
        pes13_perf8_game_env.is_any_overridden = 1;
        __atomic_store_n(&pes13_perf8_active, 1, __ATOMIC_RELEASE);
        if (&wine_nx_runtime_trace)
            wine_nx_runtime_trace("[BOX64] PERF8 block profile active: BIGBLOCK=1; other values remain Compatible");
    }
    /* Once per block translation attempt, never once per executed block. */
    __atomic_add_fetch(&pes13_perf8_builds, 1, __ATOMIC_RELAXED);
    return &pes13_perf8_game_env;
}

void wine_nx_box64_profile_status(char *out, size_t size)
{
    unsigned int active = __atomic_load_n(&pes13_perf8_active, __ATOMIC_ACQUIRE);
    const box64env_t *env = active ? &pes13_perf8_game_env : &box64env;
    snprintf(out, size,
             "enabled=%d active=%u translation_attempts=%u BIGBLOCK=%d SAFEFLAGS=%d FASTNAN=%d FASTROUND=%d STRONGMEM=%d X87DOUBLE=%d CALLRET=%d",
             pes13_perf8_enabled, active,
             __atomic_load_n(&pes13_perf8_builds, __ATOMIC_RELAXED),
             env->dynarec_bigblock, env->dynarec_safeflags,
             env->dynarec_fastnan, env->dynarec_fastround,
             env->dynarec_strongmem, env->dynarec_x87double, env->dynarec_callret);
}
#endif
