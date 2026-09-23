/* Included by runtime.c, after log_line's declaration. */
#include "pes13_perf24_metrics.h"
extern unsigned int wine_nx_perf24_sampling_epoch;
static struct pes24_hist pes24_gaps[2], pes24_host;
static uint64_t pes24_last_present;
static unsigned int pes24_boundaries;

void wine_nx_perf24_present(void)
{
    static __thread uint64_t last_tick;
    static __thread unsigned int last_epoch;
    uint64_t now = armGetSystemTick();
    unsigned int epoch = __atomic_load_n(&wine_nx_perf24_sampling_epoch, __ATOMIC_ACQUIRE);
    if (last_tick && now >= last_tick) {
        if (epoch == last_epoch)
            pes24_add(&pes24_gaps[epoch & 1], armTicksToNs(now-last_tick)/1000);
        else
            __atomic_add_fetch(&pes24_boundaries, 1, __ATOMIC_RELAXED);
    }
    last_tick = now;
    last_epoch = epoch;
    __atomic_store_n(&pes24_last_present, now, __ATOMIC_RELEASE);
}

void wine_nx_perf24_host(unsigned long long ticks)
{
    pes24_add(&pes24_host, armTicksToNs(ticks)/1000);
}

static void pes24_report_hist(const char *name, struct pes24_hist *h,
                              struct pes24_snapshot *previous)
{
    struct pes24_snapshot d = pes24_delta(h, previous);
    uint64_t n = 0;
    for (unsigned i=0; i<PES24_BUCKETS; ++i) n += d.count[i];
    log_line("[FRAME24] %s n=%llu avg_us=%llu max_since_launch_us=%llu bins=%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu",
        name, (unsigned long long)n, (unsigned long long)(n ? d.total_us/n : 0),
        (unsigned long long)d.maximum_us,
        (unsigned long long)d.count[0], (unsigned long long)d.count[1],
        (unsigned long long)d.count[2], (unsigned long long)d.count[3],
        (unsigned long long)d.count[4], (unsigned long long)d.count[5],
        (unsigned long long)d.count[6], (unsigned long long)d.count[7],
        (unsigned long long)d.count[8], (unsigned long long)d.count[9]);
}

static void pes24_report(void)
{
    static struct pes24_snapshot previous[3];
    uint64_t now = armGetSystemTick();
    uint64_t last = __atomic_load_n(&pes24_last_present, __ATOMIC_ACQUIRE);
    pes24_report_hist("gap_quiet", &pes24_gaps[0], &previous[0]);
    pes24_report_hist("gap_sampled", &pes24_gaps[1], &previous[1]);
    pes24_report_hist("host_present", &pes24_host, &previous[2]);
    log_line("[FRAME24] ever_presented=%d age_ms=%llu mixed_phase_gaps_total=%u",
        !!last, (unsigned long long)(last && now>=last ? armTicksToNs(now-last)/1000000 : 0),
        __atomic_load_n(&pes24_boundaries, __ATOMIC_RELAXED));
}
