/* LGPL-2.1-or-later. Bounded synchronization diagnostics; no hot-path I/O. */
/* Device regression in sync-pacing: keep selective routing opt-in only. */
int wine_nx_fex_targeted_wake = 0;
extern void wine_nx_fex_sync_snapshot(uint64_t out[7]);
#define FEX_DELAY_ROWS 64
struct fex_delay_row {
    unsigned tid;
    uint64_t yields, yield_us, sleeps, requested_us, actual_us, excess_us;
    uint64_t excess_peak_us, late20, other;
};
static struct fex_delay_row fex_delay_rows[FEX_DELAY_ROWS];
static uint64_t fex_delay_overflow;

void wine_nx_fex_delay_note(unsigned tid, int alertable, int has_timeout,
                          int64_t timeout, uint64_t begin, int status)
{
    uint64_t elapsed = armTicksToNs(armGetSystemTick() - begin) / 1000;
    struct fex_delay_row *r = NULL;
    unsigned i;
    /* IDs stay stable for a connection. Open addressing bounds the observer
     * even if a future game creates more sleeping threads than fit here. */
    if (!tid) return;
    for (i = 0; i < FEX_DELAY_ROWS; ++i) {
        struct fex_delay_row *p = &fex_delay_rows[((tid >> 2) + i) % FEX_DELAY_ROWS];
        unsigned key = __atomic_load_n(&p->tid, __ATOMIC_RELAXED);
        if (key == tid || (!key && __atomic_compare_exchange_n(&p->tid, &key, tid, 0,
                                                              __ATOMIC_RELAXED, __ATOMIC_RELAXED))) {
            r = p; break;
        }
    }
    if (!r) { __atomic_add_fetch(&fex_delay_overflow, 1, __ATOMIC_RELAXED); return; }
    if (!alertable && has_timeout && !timeout) {
        __atomic_add_fetch(&r->yields, 1, __ATOMIC_RELAXED);
        __atomic_add_fetch(&r->yield_us, elapsed, __ATOMIC_RELAXED);
    } else if (!alertable && has_timeout && timeout < 0 && !status) {
        uint64_t requested = (0ULL - (uint64_t)timeout) / 10;
        uint64_t excess = elapsed > requested ? elapsed - requested : 0;
        uint64_t peak = __atomic_load_n(&r->excess_peak_us, __ATOMIC_RELAXED);
        __atomic_add_fetch(&r->sleeps, 1, __ATOMIC_RELAXED);
        __atomic_add_fetch(&r->requested_us, requested, __ATOMIC_RELAXED);
        __atomic_add_fetch(&r->actual_us, elapsed, __ATOMIC_RELAXED);
        __atomic_add_fetch(&r->excess_us, excess, __ATOMIC_RELAXED);
        if (excess >= 20000) __atomic_add_fetch(&r->late20, 1, __ATOMIC_RELAXED);
        while (excess > peak && !__atomic_compare_exchange_n(&r->excess_peak_us, &peak, excess, 1,
                                                            __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}
    } else __atomic_add_fetch(&r->other, 1, __ATOMIC_RELAXED);
}

static void fex_sync_report(void)
{
    static uint64_t previous[7], previous_overflow;
    static struct fex_delay_row prev[FEX_DELAY_ROWS];
    uint64_t now[7], d[7], overflow;
    unsigned i;
    wine_nx_fex_sync_snapshot(now);
    for (i = 0; i < 7; ++i) { d[i] = now[i] - previous[i]; previous[i] = now[i]; }
    log_line("[FEX3-SYNC] targeted=%llu notices=%llu broad=%llu candidates=%llu notified=%llu filtered=%llu sleeps=%llu",
             (unsigned long long)now[0], (unsigned long long)d[1], (unsigned long long)d[2],
             (unsigned long long)d[3], (unsigned long long)d[4], (unsigned long long)d[5], (unsigned long long)d[6]);
    for (i = 0; i < FEX_DELAY_ROWS; ++i) {
        struct fex_delay_row *r = &fex_delay_rows[i], cur, delta;
        cur.tid = __atomic_load_n(&r->tid, __ATOMIC_RELAXED);
        if (!cur.tid) continue;
#define FEX_DELAY_COPY(field) cur.field = __atomic_load_n(&r->field, __ATOMIC_RELAXED); \
        delta.field = cur.field - prev[i].field
        FEX_DELAY_COPY(yields); FEX_DELAY_COPY(yield_us); FEX_DELAY_COPY(sleeps);
        FEX_DELAY_COPY(requested_us); FEX_DELAY_COPY(actual_us); FEX_DELAY_COPY(excess_us);
        FEX_DELAY_COPY(late20); FEX_DELAY_COPY(other);
#undef FEX_DELAY_COPY
        cur.excess_peak_us = __atomic_load_n(&r->excess_peak_us, __ATOMIC_RELAXED);
        prev[i] = cur;
        if (!delta.yields && !delta.sleeps && !delta.other) continue;
        log_line("[FEX3-DELAY] tid=%u yields=%llu yield_us=%llu sleeps=%llu requested_us=%llu actual_us=%llu excess_us=%llu excess_peak_us=%llu late20=%llu other=%llu",
                 cur.tid, (unsigned long long)delta.yields, (unsigned long long)delta.yield_us,
                 (unsigned long long)delta.sleeps, (unsigned long long)delta.requested_us,
                 (unsigned long long)delta.actual_us, (unsigned long long)delta.excess_us,
                 (unsigned long long)cur.excess_peak_us, (unsigned long long)delta.late20,
                 (unsigned long long)delta.other);
    }
    overflow = __atomic_load_n(&fex_delay_overflow, __ATOMIC_RELAXED);
    if (overflow != previous_overflow) log_line("[FEX3-DELAY] overflow=%llu", (unsigned long long)(overflow - previous_overflow));
    previous_overflow = overflow;
}
