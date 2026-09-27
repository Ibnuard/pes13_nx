/* LGPL-2.1-or-later. Bounded, cumulative backoff statistics; logger only I/O. */
int wine_nx_fex_yield_backoff;
#define FEX_YIELD_ROWS 64
static struct {
    unsigned tid;
    uint64_t pauses, actual_us, peak_us, late2ms;
} fex_yield_rows[FEX_YIELD_ROWS];
static uint64_t fex_yield_overflow;

void wine_nx_fex_yield_pause_note(unsigned tid, uint64_t elapsed_us)
{
    if (!tid) return;
    for (unsigned i = 0; i < FEX_YIELD_ROWS; ++i) {
        unsigned slot = ((tid >> 2) + i) % FEX_YIELD_ROWS;
        unsigned key = __atomic_load_n(&fex_yield_rows[slot].tid, __ATOMIC_RELAXED);
        if (key != tid && (key || !__atomic_compare_exchange_n(&fex_yield_rows[slot].tid,
              &key, tid, 0, __ATOMIC_RELAXED, __ATOMIC_RELAXED))) continue;
        __atomic_add_fetch(&fex_yield_rows[slot].pauses, 1, __ATOMIC_RELAXED);
        __atomic_add_fetch(&fex_yield_rows[slot].actual_us, elapsed_us, __ATOMIC_RELAXED);
        if (elapsed_us >= 2000) __atomic_add_fetch(&fex_yield_rows[slot].late2ms, 1, __ATOMIC_RELAXED);
        uint64_t peak = __atomic_load_n(&fex_yield_rows[slot].peak_us, __ATOMIC_RELAXED);
        while (elapsed_us > peak && !__atomic_compare_exchange_n(&fex_yield_rows[slot].peak_us,
                &peak, elapsed_us, 1, __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}
        return;
    }
    __atomic_add_fetch(&fex_yield_overflow, 1, __ATOMIC_RELAXED);
}

static void fex_yield_report(void)
{
    static uint64_t previous[FEX_YIELD_ROWS], previous_overflow;
    for (unsigned i = 0; i < FEX_YIELD_ROWS; ++i) {
        unsigned tid = __atomic_load_n(&fex_yield_rows[i].tid, __ATOMIC_RELAXED);
        uint64_t pauses = __atomic_load_n(&fex_yield_rows[i].pauses, __ATOMIC_RELAXED);
        if (!tid || pauses == previous[i]) continue;
        previous[i] = pauses;
        log_line("[FEX3-YIELD] tid=%u pauses=%llu requested_us=%llu actual_us=%llu peak_us=%llu late2ms=%llu; cumulative",
                 tid, (unsigned long long)pauses, (unsigned long long)(pauses * 50),
                 (unsigned long long)__atomic_load_n(&fex_yield_rows[i].actual_us, __ATOMIC_RELAXED),
                 (unsigned long long)__atomic_load_n(&fex_yield_rows[i].peak_us, __ATOMIC_RELAXED),
                 (unsigned long long)__atomic_load_n(&fex_yield_rows[i].late2ms, __ATOMIC_RELAXED));
    }
    uint64_t overflow = __atomic_load_n(&fex_yield_overflow, __ATOMIC_RELAXED);
    if (overflow != previous_overflow) log_line("[FEX3-YIELD] overflow=%llu", (unsigned long long)overflow);
    previous_overflow = overflow;
}
