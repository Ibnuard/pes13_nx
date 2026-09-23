#include "pes13_perf30_core.h"
static uint64_t pes30_clock(void) { return armGetSystemTick(); }
static unsigned pes30_handle(void) { return threadGetCurHandle(); }
static uint64_t pes30_to_us(uint64_t ticks) { return armTicksToNs(ticks)/1000; }
static const char *pes30_names[PES30_STAGES]={"queue_lock","queue_driver","queue_state","upload_flush",
    "upload_wait","queue_wait","commands","signal","host_sync","channel_submit","channel_lock",
    "order_lock","reserve","throttle","kickoff","audio_lock","audio_pump","audio_release"};
void wine_nx_perf30_init(void)
{
    FILE *f=fopen("sdmc:/switch/pes13-nx/perf30-submit-diagnostics.txt","r");
    unsigned enabled=f ? fgetc(f)=='1' : 1;
    if(f) fclose(f);
    __atomic_store_n(&pes30_enabled,enabled,__ATOMIC_RELEASE);
}
static void pes30_report(void)
{
    static struct pes30_total previous[PES30_STAGES];
    unsigned enabled=__atomic_load_n(&pes30_enabled,__ATOMIC_RELAXED);
    log_line("[PERF30] submit_diagnostics=%u owners=%u owner_overflow=%u slow_event_drops=%u; nested host wall times, not GPU time",
        enabled,__atomic_load_n(&pes30_next_owner,__ATOMIC_RELAXED),
        __atomic_load_n(&pes30_owner_overflow,__ATOMIC_RELAXED),__atomic_load_n(&pes30_event_drops,__ATOMIC_RELAXED));
    if(!enabled) return;
    for(unsigned i=0;i<PES30_STAGES;++i) {
        struct pes30_total now={__atomic_load_n(&pes30_totals[i].calls,__ATOMIC_RELAXED),
            __atomic_load_n(&pes30_totals[i].ticks,__ATOMIC_RELAXED),
            __atomic_load_n(&pes30_totals[i].maximum,__ATOMIC_RELAXED),
            __atomic_load_n(&pes30_totals[i].slow,__ATOMIC_RELAXED)};
        uint64_t n=now.calls-previous[i].calls,ticks=now.ticks-previous[i].ticks;
        if(n) log_line("[STAGE30] %s n=%llu total_us=%llu gt100ms=%llu max_since_launch_us=%llu",
            pes30_names[i],(unsigned long long)n,(unsigned long long)pes30_to_us(ticks),
            (unsigned long long)(now.slow-previous[i].slow),(unsigned long long)pes30_to_us(now.maximum));
        previous[i]=now;
    }
    uint64_t now=pes30_clock();
    for(unsigned i=0;i<PES30_OWNERS;++i) {
        struct pes30_owner owner;
        if(!pes30_snapshot(i,&owner) || owner.stage>=PES30_STAGES || now<owner.start) continue;
        uint64_t age=pes30_to_us(now-owner.start);
        if(age>=100000) log_line("[ACTIVE30] owner_slot=%u handle=%x stage=%s object=%llx age_us=%llu",
            i,owner.handle,pes30_names[owner.stage],(unsigned long long)owner.object,(unsigned long long)age);
    }
    for(unsigned i=0;i<PES30_EVENTS;++i) {
        struct pes30_event *e=&pes30_events[i];
        if(__atomic_load_n(&e->state,__ATOMIC_ACQUIRE)!=2) continue;
        log_line("[SLOW30] handle=%x stage=%s object=%llx start_tick=%llu us=%llu",e->handle,pes30_names[e->stage],
            (unsigned long long)e->object,(unsigned long long)e->start,(unsigned long long)pes30_to_us(e->ticks));
        __atomic_store_n(&e->state,0,__ATOMIC_RELEASE);
    }
    static const char *value_names[PES30_VALUES]={"slm_warp","slm_tpc","image_pool","sampler_pool","audio_held","audio_submitted","audio_played"};
    for(unsigned i=0;i<PES30_VALUES;++i)
        log_line("[VALUE30] %s last=%llu max_since_launch=%llu",value_names[i],
            (unsigned long long)__atomic_load_n(&pes30_values[i],__ATOMIC_RELAXED),
            (unsigned long long)__atomic_load_n(&pes30_peaks[i],__ATOMIC_RELAXED));
}
