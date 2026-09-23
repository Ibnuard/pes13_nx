/* Bounded, lock-free CPU wall-time histograms. No file I/O on the hot path. */
#include "pes13_perf44_metrics.h"
#include "pes13_perf24_metrics.h"
static struct pes24_hist pes44_stages[PES44_STAGES];

void wine_nx_perf44_span(unsigned int stage, unsigned long long ticks)
{
    if (stage < PES44_STAGES)
        pes24_add(&pes44_stages[stage], armTicksToNs(ticks) / 1000);
}

static void pes44_report(void)
{
    static const char *names[PES44_STAGES] = {
        "present_total", "present_lock", "surface_before", "surface_after",
        "acquire_host", "submit_host", "fence_host", "semaphore_host",
        "idle_host"
    };
    static struct pes24_snapshot previous[PES44_STAGES];
    for (unsigned i = 0; i < PES44_STAGES; ++i) {
        struct pes24_snapshot d = pes24_delta(&pes44_stages[i], &previous[i]);
        uint64_t n = 0, over = 0;
        for (unsigned j = 0; j < PES24_BUCKETS; ++j) {
            n += d.count[j];
            if (j >= 1) over += d.count[j];
        }
        if (!n) continue;
        log_line("[PIPE44] %s n=%llu total_us=%llu avg_us=%llu gt16ms=%llu max_since_launch_us=%llu",
            names[i], (unsigned long long)n, (unsigned long long)d.total_us,
            (unsigned long long)(d.total_us / n), (unsigned long long)over,
            (unsigned long long)d.maximum_us);
    }
}
