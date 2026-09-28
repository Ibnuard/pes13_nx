/* LGPL-2.1-or-later. Bounded records, no file I/O or thread pausing on Present.
 * CPU tick deltas concern only the presenting thread, not a whole core. */
static int fex_gap_probe_enabled = 1;
struct fex_gap_sample {
    uint64_t tick, wall_us, cpu_us, pipeline_us[4];
    unsigned handle, cpu_valid;
};
static struct {
    pthread_mutex_t mutex;
    unsigned count;
    struct fex_gap_sample rows[32];
    uint64_t dropped;
} fex_gaps = {.mutex = PTHREAD_MUTEX_INITIALIZER};
static __thread uint64_t fex_gap_pipeline_us[4];

static void fex_gap_pipeline_note(unsigned stage, uint64_t elapsed_us)
{
    if (fex_gap_probe_enabled && stage < 4) fex_gap_pipeline_us[stage] += elapsed_us;
}

static void fex_gap_present(uint64_t queue, uint64_t swapchain, int valid)
{
    static __thread uint64_t previous_wall, previous_cpu, previous_queue, previous_swapchain;
    static __thread unsigned previous_valid;
    uint64_t cpu = 0, now;
    unsigned cpu_valid;
    struct fex_gap_sample sample = {0};
    if (!fex_gap_probe_enabled) return;
    if (!valid) {
        previous_wall = previous_valid = 0;
        memset(fex_gap_pipeline_us, 0, sizeof(fex_gap_pipeline_us));
        return;
    }
    /* Existing profiler uses the same kernel counter, in system-tick units. */
    cpu_valid = R_SUCCEEDED(svcGetInfo(&cpu, InfoType_ThreadTickCount, threadGetCurHandle(), UINT64_MAX));
    now = armGetSystemTick();
    if (previous_wall && now >= previous_wall && queue == previous_queue && swapchain == previous_swapchain) {
        sample.wall_us = armTicksToNs(now - previous_wall) / 1000;
        if (sample.wall_us > 50000) {
            sample.tick = now;
            sample.handle = threadGetCurHandle();
            sample.cpu_valid = cpu_valid && previous_valid && cpu >= previous_cpu;
            if (sample.cpu_valid) sample.cpu_us = armTicksToNs(cpu - previous_cpu) / 1000;
            if (sample.cpu_us > sample.wall_us + 1000) sample.cpu_valid = 0;
            memcpy(sample.pipeline_us, fex_gap_pipeline_us, sizeof(sample.pipeline_us));
            if (pthread_mutex_trylock(&fex_gaps.mutex)) {
                __atomic_add_fetch(&fex_gaps.dropped, 1, __ATOMIC_RELAXED);
            } else {
                if (fex_gaps.count < 32) fex_gaps.rows[fex_gaps.count++] = sample;
                else __atomic_add_fetch(&fex_gaps.dropped, 1, __ATOMIC_RELAXED);
                pthread_mutex_unlock(&fex_gaps.mutex);
            }
        }
    }
    previous_wall = now; previous_cpu = cpu; previous_valid = cpu_valid;
    previous_queue = queue; previous_swapchain = swapchain;
    memset(fex_gap_pipeline_us, 0, sizeof(fex_gap_pipeline_us));
}

static void fex_gap_report(void)
{
    struct fex_gap_sample rows[32];
    unsigned count;
    uint64_t dropped;
    if (!fex_gap_probe_enabled || pthread_mutex_trylock(&fex_gaps.mutex)) return;
    count = fex_gaps.count;
    memcpy(rows, fex_gaps.rows, count * sizeof(*rows));
    fex_gaps.count = 0;
    pthread_mutex_unlock(&fex_gaps.mutex);
    dropped = __atomic_exchange_n(&fex_gaps.dropped, 0, __ATOMIC_RELAXED);
    for (unsigned i = 0; i < count; ++i) {
        const struct fex_gap_sample *s = &rows[i];
        log_line("[FEX3-GAP] tick=%llu handle=%u end_gap_us=%llu cpu_valid=%u thread_cpu_us=%llu acquire_us=%llu submit_us=%llu fence_us=%llu semaphore_us=%llu",
                 (unsigned long long)s->tick, s->handle, (unsigned long long)s->wall_us,
                 s->cpu_valid, (unsigned long long)s->cpu_us,
                 (unsigned long long)s->pipeline_us[0], (unsigned long long)s->pipeline_us[1],
                 (unsigned long long)s->pipeline_us[2], (unsigned long long)s->pipeline_us[3]);
    }
    if (count || dropped) log_line("[FEX3-GAP] recorded=%u dropped=%llu; present-thread only, intervals end after Present, waits include scheduling",
                                  count, (unsigned long long)dropped);
}
