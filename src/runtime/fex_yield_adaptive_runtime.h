/* LGPL-2.1-or-later. Logger-only output, allocation-free producer counters. */
int wine_nx_fex_yield_adaptive;
static uint64_t fex_yield_initial, fex_yield_sustained, fex_yield_cooldowns;

void wine_nx_fex_yield_adaptive_note(int sustained, int cooldown)
{
    __atomic_add_fetch(sustained ? &fex_yield_sustained : &fex_yield_initial, 1, __ATOMIC_RELAXED);
    if (cooldown) __atomic_add_fetch(&fex_yield_cooldowns, 1, __ATOMIC_RELAXED);
}

static void fex_yield_adaptive_report(void)
{
    static uint64_t prev_initial, prev_sustained, prev_cooldowns;
    uint64_t initial = __atomic_load_n(&fex_yield_initial, __ATOMIC_RELAXED);
    uint64_t sustained = __atomic_load_n(&fex_yield_sustained, __ATOMIC_RELAXED);
    uint64_t cooldowns = __atomic_load_n(&fex_yield_cooldowns, __ATOMIC_RELAXED);
    if (initial == prev_initial && sustained == prev_sustained && cooldowns == prev_cooldowns) return;
    log_line("[FEX3-YIELD-ADAPT] initial=%llu sustained=%llu cooldowns=%llu; cumulative",
             (unsigned long long)initial, (unsigned long long)sustained, (unsigned long long)cooldowns);
    prev_initial = initial; prev_sustained = sustained; prev_cooldowns = cooldowns;
}
