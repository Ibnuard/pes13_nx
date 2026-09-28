/* LGPL-2.1-or-later. Passive CPU wall-time measurements, not GPU timestamps.
 * Called after existing driver calls or USD clock updates. No allocation,
 * sleeping, guest-clock writes, or logging on these paths. */
#define FEX_PIPE_STAGES 5
static struct fex_frame_hist fex_pipeline_stats[FEX_PIPE_STAGES];
static uint64_t fex_pipeline_timeouts[FEX_PIPE_STAGES], fex_pipeline_errors[FEX_PIPE_STAGES];
static uint64_t fex_pipeline_invalid;

void wine_nx_fex_pipeline_note(unsigned stage, uint64_t begin, int result)
{
    uint64_t end = armGetSystemTick();
    if (stage >= FEX_PIPE_STAGES - 1 || end < begin) {
        __atomic_add_fetch(&fex_pipeline_invalid, 1, __ATOMIC_RELAXED);
        return;
    }
    fex_frame_add(&fex_pipeline_stats[stage], armTicksToNs(end - begin) / 1000);
    /* VK_TIMEOUT=2. A failed/timeout call still consumed wall time. */
    if (result == 2) __atomic_add_fetch(&fex_pipeline_timeouts[stage], 1, __ATOMIC_RELAXED);
    if (result < 0) __atomic_add_fetch(&fex_pipeline_errors[stage], 1, __ATOMIC_RELAXED);
}

void wine_nx_fex_shared_clock_note(uint64_t interrupt_time)
{
    /* One producer: usd_clock_thread (plus its synchronous initialization).
     * This is the existing, unscaled 100-ns InterruptTime value. */
    static uint64_t previous;
    if (previous && interrupt_time >= previous)
        fex_frame_add(&fex_pipeline_stats[4], (interrupt_time - previous) / 10);
    else if (previous)
        __atomic_add_fetch(&fex_pipeline_invalid, 1, __ATOMIC_RELAXED);
    previous = interrupt_time;
}

static void fex_pipeline_report(void)
{
    static struct fex_frame_hist previous[FEX_PIPE_STAGES];
    static uint64_t timeouts[FEX_PIPE_STAGES], errors[FEX_PIPE_STAGES];
    static const char *names[FEX_PIPE_STAGES] = {
        "acquire_driver", "submit_driver", "fence_wait", "semaphore_wait", "shared_clock_gap"
    };
    unsigned i, b;
    for (i = 0; i < FEX_PIPE_STAGES; ++i) {
        struct fex_frame_hist d = fex_frame_delta(&fex_pipeline_stats[i], &previous[i]);
        uint64_t t = __atomic_load_n(&fex_pipeline_timeouts[i], __ATOMIC_RELAXED);
        uint64_t e = __atomic_load_n(&fex_pipeline_errors[i], __ATOMIC_RELAXED), n = 0;
        for (b = 0; b < FEX_FRAME_BINS; ++b) n += d.bins[b];
        log_line("[FEX3-PIPE] %s n=%llu avg_us=%llu peak_since_launch_us=%llu timeout=%llu errors=%llu bins=%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu",
                 names[i], (unsigned long long)n, (unsigned long long)(n ? d.sum_us / n : 0),
                 (unsigned long long)d.peak_us, (unsigned long long)(t - timeouts[i]),
                 (unsigned long long)(e - errors[i]),
                 (unsigned long long)d.bins[0], (unsigned long long)d.bins[1],
                 (unsigned long long)d.bins[2], (unsigned long long)d.bins[3],
                 (unsigned long long)d.bins[4], (unsigned long long)d.bins[5],
                 (unsigned long long)d.bins[6], (unsigned long long)d.bins[7],
                 (unsigned long long)d.bins[8]);
        timeouts[i] = t; errors[i] = e;
    }
    log_line("[FEX3-PIPE] invalid_since_launch=%llu; wait times include parking/scheduling, not GPU execution",
             (unsigned long long)__atomic_load_n(&fex_pipeline_invalid, __ATOMIC_RELAXED));
}
