/* LGPL-2.1-or-later. CPU wall times, not GPU timestamps. No hot-path logging,
 * allocation, sleep, thread suspension, or changes to driver/cache results. */
static struct fex_frame_hist fex_warm_stats[3];
static uint64_t fex_warm_hits, fex_warm_misses, fex_warm_errors[2];
struct disk_cache;
extern void *__real_disk_cache_get(struct disk_cache *, const unsigned char *, size_t *);

void *__wrap_disk_cache_get(struct disk_cache *cache, const unsigned char *key, size_t *size)
{
    uint64_t begin = armGetSystemTick();
    void *result = __real_disk_cache_get(cache, key, size);
    fex_frame_add(&fex_warm_stats[2], armTicksToNs(armGetSystemTick() - begin) / 1000);
    if (result) __atomic_add_fetch(&fex_warm_hits, 1, __ATOMIC_RELAXED);
    else __atomic_add_fetch(&fex_warm_misses, 1, __ATOMIC_RELAXED);
    return result;
}

void wine_nx_fex_compile_note(unsigned stage, uint64_t begin, int result)
{
    uint64_t end = armGetSystemTick();
    if (stage >= 2 || end < begin) return;
    fex_frame_add(&fex_warm_stats[stage], armTicksToNs(end - begin) / 1000);
    if (result < 0) __atomic_add_fetch(&fex_warm_errors[stage], 1, __ATOMIC_RELAXED);
}

/* Existing log thread, once per ten-second frame report. Completed calls
 * may overlap on different threads, so summed time is not a frame budget. */
static void fex_warm_report(void)
{
    static struct fex_frame_hist previous[3];
    static uint64_t old_hits, old_misses, old_deferred, old_errors[2];
    static const char *const names[] = {"graphics_pipeline", "compute_pipeline", "driver_cache_get"};
    unsigned i, b;
    uint64_t hits = __atomic_load_n(&fex_warm_hits, __ATOMIC_RELAXED);
    uint64_t misses = __atomic_load_n(&fex_warm_misses, __ATOMIC_RELAXED);
    uint64_t deferred = __atomic_load_n(&fex_warm_deferred, __ATOMIC_RELAXED);
    for (i = 0; i < 3; ++i) {
        struct fex_frame_hist d = fex_frame_delta(&fex_warm_stats[i], &previous[i]);
        uint64_t n = 0, slow50 = 0;
        uint64_t errors = i < 2 ? __atomic_load_n(&fex_warm_errors[i], __ATOMIC_RELAXED) : 0;
        for (b = 0; b < FEX_FRAME_BINS; ++b) n += d.bins[b];
        for (b = 5; b < FEX_FRAME_BINS; ++b) slow50 += d.bins[b];
        log_line("[FEX3-WARM] %s n=%llu total_us=%llu avg_us=%llu peak_since_launch_us=%llu over50ms=%llu errors=%llu",
                 names[i], (unsigned long long)n, (unsigned long long)d.sum_us,
                 (unsigned long long)(n ? d.sum_us / n : 0), (unsigned long long)d.peak_us,
                 (unsigned long long)slow50,
                 (unsigned long long)(i < 2 ? errors - old_errors[i] : 0));
        if (i < 2) old_errors[i] = errors;
    }
    log_line("[FEX3-WARM] driver_cache_hits=%llu misses=%llu routine_flushes_deferred=%llu; CPU wall time, cache hits can include this run",
             (unsigned long long)(hits - old_hits), (unsigned long long)(misses - old_misses),
             (unsigned long long)(deferred - old_deferred));
    old_hits = hits; old_misses = misses; old_deferred = deferred;
}
