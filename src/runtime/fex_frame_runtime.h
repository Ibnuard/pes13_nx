/* LGPL-2.1-or-later. Included in runtime.c before the log flusher.
 * Raw ticks belong to libnx's physical counter. No guest-clock modification.
 * Stream history is thread-local so different queues/swapchains are not
 * interpreted as a burst of frames from the PES swapchain. */
static void log_line(const char *fmt, ...);
static struct fex_frame_hist fex_frame_stats[4];
static uint64_t fex_frame_ok, fex_frame_errors, fex_frame_bursts, fex_frame_last;

uint64_t wine_nx_fex_frame_tick(void)
{
    return armGetSystemTick();
}

void wine_nx_fex_frame_note(uint64_t queue, uint64_t swapchain, uint64_t begin,
                           uint64_t lock_begin, uint64_t host_begin,
                           uint64_t host_end, int result)
{
    static __thread uint64_t last_queue, last_swapchain, last_begin, last_gap_us;
    uint64_t end = armGetSystemTick();
    uint64_t gap_us = 0;
    int ordered = end >= begin && (!host_begin ||
                  (lock_begin >= begin && host_begin >= lock_begin &&
                   host_end >= host_begin && end >= host_end));
    if (result < 0 || !swapchain || !ordered) {
        __atomic_add_fetch(&fex_frame_errors, 1, __ATOMIC_RELAXED);
        last_begin = last_gap_us = 0;
        return;
    }
    if (last_begin && begin >= last_begin && queue == last_queue && swapchain == last_swapchain) {
        gap_us = armTicksToNs(begin - last_begin) / 1000;
        fex_frame_add(&fex_frame_stats[0], gap_us);
        if (last_gap_us >= 50000 && gap_us < 8000)
            __atomic_add_fetch(&fex_frame_bursts, 1, __ATOMIC_RELAXED);
    }
    fex_frame_add(&fex_frame_stats[1], armTicksToNs(end - begin) / 1000);
    if (host_begin) {
        fex_frame_add(&fex_frame_stats[2], armTicksToNs(host_begin - lock_begin) / 1000);
        fex_frame_add(&fex_frame_stats[3], armTicksToNs(host_end - host_begin) / 1000);
    }
    last_queue = queue;
    last_swapchain = swapchain;
    last_begin = begin;
    last_gap_us = gap_us;
    __atomic_add_fetch(&fex_frame_ok, 1, __ATOMIC_RELAXED);
    __atomic_store_n(&fex_frame_last, end, __ATOMIC_RELAXED);
}

/* Called only by log_flusher, every ~10s throughout the run. Formatting and
 * SD writes never run inside vkQueuePresentKHR. No thread sampling/pausing. */
static void fex_frame_report(void)
{
    static struct fex_frame_hist previous[4];
    static uint64_t start, last_report, last_ok, last_errors, last_bursts;
    static const char *names[4] = {"entry_gap", "native_total", "present_lock", "driver_call"};
    uint64_t now = armGetSystemTick();
    uint64_t ok = __atomic_load_n(&fex_frame_ok, __ATOMIC_RELAXED);
    uint64_t errors = __atomic_load_n(&fex_frame_errors, __ATOMIC_RELAXED);
    uint64_t bursts = __atomic_load_n(&fex_frame_bursts, __ATOMIC_RELAXED);
    uint64_t last = __atomic_load_n(&fex_frame_last, __ATOMIC_RELAXED);
    unsigned i;
    if (!start) start = now;
    log_line("[FEX3-PACE] elapsed_ms=%llu window_ms=%llu ok=%llu errors=%llu gap50_then_lt8=%llu age_ms=%llu",
             (unsigned long long)(armTicksToNs(now - start) / 1000000),
             (unsigned long long)(last_report ? armTicksToNs(now - last_report) / 1000000 : 0),
             (unsigned long long)(ok - last_ok), (unsigned long long)(errors - last_errors),
             (unsigned long long)(bursts - last_bursts),
             (unsigned long long)(last && now >= last ? armTicksToNs(now - last) / 1000000 : 0));
    last_report = now; last_ok = ok; last_errors = errors; last_bursts = bursts;
    for (i = 0; i < 4; ++i) {
        struct fex_frame_hist d = fex_frame_delta(&fex_frame_stats[i], &previous[i]);
        uint64_t n = 0;
        unsigned b;
        for (b = 0; b < FEX_FRAME_BINS; ++b) n += d.bins[b];
        log_line("[FEX3-PACE] %s n=%llu avg_us=%llu peak_since_launch_us=%llu bins=%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu",
                 names[i], (unsigned long long)n, (unsigned long long)(n ? d.sum_us / n : 0),
                 (unsigned long long)d.peak_us,
                 (unsigned long long)d.bins[0], (unsigned long long)d.bins[1],
                 (unsigned long long)d.bins[2], (unsigned long long)d.bins[3],
                 (unsigned long long)d.bins[4], (unsigned long long)d.bins[5],
                 (unsigned long long)d.bins[6], (unsigned long long)d.bins[7],
                 (unsigned long long)d.bins[8]);
    }
}
