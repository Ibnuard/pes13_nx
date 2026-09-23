#include "pes13_perf27_metrics.h"
#include "pes13_perf24_metrics.h"
static struct pes24_hist pes27_stages[PES27_STAGES];
void wine_nx_perf27_span(unsigned int stage, unsigned long long ticks)
{
    if (stage < PES27_STAGES) pes24_add(&pes27_stages[stage], armTicksToNs(ticks)/1000);
}
static void pes27_report(void)
{
    static const char *names[] = {"present_total", "present_lock", "surface_before",
        "surface_after", "acquire_host", "submit_host", "fence_host", "semaphore_host", "idle_host"};
    static struct pes24_snapshot previous[PES27_STAGES];
    static unsigned long long last_sync[7];
    unsigned long long sync[7], delta[7];
    extern void wine_nx_perf27_sync_snapshot(unsigned long long *);
    wine_nx_perf27_sync_snapshot(sync);
    for (unsigned i=0; i<7; ++i) { delta[i]=sync[i]-last_sync[i]; last_sync[i]=sync[i]; }
    log_line("[SYNC27] targeted=%llu notices=%llu broad=%llu candidates=%llu notified=%llu filtered=%llu sleeps=%llu",
        sync[0],delta[1],delta[2],delta[3],delta[4],delta[5],delta[6]);
    for (unsigned i=0; i<PES27_STAGES; ++i) {
        struct pes24_snapshot d=pes24_delta(&pes27_stages[i], &previous[i]);
        uint64_t n=0, over=0;
        for (unsigned j=0; j<PES24_BUCKETS; ++j) { n+=d.count[j]; if(j>=1) over+=d.count[j]; }
        if (!n) continue;
        log_line("[PIPE27] %s n=%llu total_us=%llu avg_us=%llu gt16ms=%llu max_since_launch_us=%llu",
            names[i],(unsigned long long)n,(unsigned long long)d.total_us,
            (unsigned long long)(n ? d.total_us/n : 0),(unsigned long long)over,
            (unsigned long long)d.maximum_us);
    }
}
