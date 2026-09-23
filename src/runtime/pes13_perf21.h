/* Compile-time-only FASTROUND selection. Included after PERF20 declarations.
 * GetCurEnvByAddr runs under the existing translator mutex. Never modify
 * box64env while guest threads are running. */
#ifndef PES13_PERF21_H
#define PES13_PERF21_H
static int pes21_mode;
static box64env_t pes21_env;
static unsigned int pes21_active, pes21_selected, pes21_completed;
static unsigned int pes21_boot_fallback, pes21_scope_fallback;
#define PES21_TEXT_BEGIN ((uintptr_t)0x401000)
#define PES21_TEXT_END   ((uintptr_t)0x13d1000)
#define PES21_MATRIX_BEGIN ((uintptr_t)0x112f000)
#define PES21_MATRIX_END   ((uintptr_t)0x1130000)

static int pes21_in_scope(uintptr_t addr)
{
    return addr >= PES21_TEXT_BEGIN && addr < PES21_TEXT_END &&
           !(addr >= PES21_MATRIX_BEGIN && addr < PES21_MATRIX_END);
}

static box64env_t *pes21_select(uintptr_t addr)
{
    if (!pes21_mode || !pes17_check_image()) return &box64env;
    if (!pes21_in_scope(addr)) {
        __atomic_add_fetch(&pes21_scope_fallback, 1, __ATOMIC_RELAXED);
        return &box64env;
    }
    if (!__atomic_load_n(&wine_nx_vk_successful_presents, __ATOMIC_ACQUIRE)) {
        __atomic_add_fetch(&pes21_boot_fallback, 1, __ATOMIC_RELAXED);
        return &box64env;
    }
    if (!__atomic_load_n(&pes21_active, __ATOMIC_RELAXED)) {
        pes21_env = box64env;
        pes21_env.dynarec_fastround = 1;
        pes21_env.is_dynarec_fastround_overridden = 1;
        pes21_env.is_any_overridden = 1;
        __atomic_store_n(&pes21_active, 1, __ATOMIC_RELEASE);
    }
    __atomic_add_fetch(&pes21_selected, 1, __ATOMIC_RELAXED);
    return &pes21_env;
}

/* Native pass checks addr > end on a page transition. Keep extension away
 * from the matrix page and from sections after .text. End is inclusive. */
uintptr_t wine_nx_perf21_block_end(uintptr_t start, uintptr_t end, const void *env)
{
    if (env != &pes21_env || !pes21_in_scope(start)) return end;
    uintptr_t limit = start < PES21_MATRIX_BEGIN ? PES21_MATRIX_BEGIN : PES21_TEXT_END;
    return end >= limit ? limit-1 : end;
}

void wine_nx_perf21_completed(void *opaque, const void *env)
{
    if (env == &pes21_env) {
        __atomic_add_fetch(&pes21_completed, 1, __ATOMIC_RELAXED);
        wine_nx_perf20_capture(opaque);
    } else if (!pes21_mode) {
        wine_nx_perf20_capture(opaque);
    }
}

void wine_nx_perf21_report(void)
{
    char line[320];
    unsigned int active = __atomic_load_n(&pes21_active, __ATOMIC_ACQUIRE);
    const box64env_t *env = active ? &pes21_env : &box64env;
    snprintf(line, sizeof(line),
        "[PERF21] enabled=%d active=%u selected=%u completed=%u boot_fallback=%u scope_fallback=%u game_FASTROUND=%d baseline_FASTROUND=%d SAFEFLAGS=%d FASTNAN=%d X87DOUBLE=%d STRONGMEM=%d BIGBLOCK=%d CALLRET=%d",
        __atomic_load_n(&pes21_mode, __ATOMIC_ACQUIRE), active,
        __atomic_load_n(&pes21_selected, __ATOMIC_RELAXED),
        __atomic_load_n(&pes21_completed, __ATOMIC_RELAXED),
        __atomic_load_n(&pes21_boot_fallback, __ATOMIC_RELAXED),
        __atomic_load_n(&pes21_scope_fallback, __ATOMIC_RELAXED),
        env->dynarec_fastround, box64env.dynarec_fastround,
        env->dynarec_safeflags, env->dynarec_fastnan, env->dynarec_x87double,
        env->dynarec_strongmem, env->dynarec_bigblock, env->dynarec_callret);
    if (&wine_nx_runtime_trace) wine_nx_runtime_trace(line);
}
#endif
