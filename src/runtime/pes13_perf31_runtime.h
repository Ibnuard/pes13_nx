#include "pes13_perf31_core.h"
static uint64_t pes31_clock(void) { return armGetSystemTick(); }
static unsigned pes31_handle(void) { return threadGetCurHandle(); }
static uint64_t pes31_to_us(uint64_t ticks) { return armTicksToNs(ticks)/1000; }
static const char *pes31_names[PES31_STAGES]={"queue_lock","queue_driver","queue_state","upload_flush",
    "upload_wait","queue_wait","commands","signal","host_sync","channel_submit","channel_lock",
    "order_lock","reserve","throttle","kickoff","audio_lock","audio_pump","audio_release","submit_api","submit_create","submit_destroy","signal_unwrap","timeline_install","timeline_gc","fence_query","fence_wait","error_scan"};
static unsigned pes31_poll_enabled;
static uint64_t pes31_poll_checked, pes31_poll_deferred;
int wine_nx_perf31_poll_mode(void) { return __atomic_load_n(&pes31_poll_enabled,__ATOMIC_RELAXED); }
void wine_nx_perf31_poll_count(int deferred) {
    __atomic_add_fetch(deferred ? &pes31_poll_deferred : &pes31_poll_checked,1,__ATOMIC_RELAXED);
}
void wine_nx_perf31_init(void)
{
    FILE *f=fopen("sdmc:/switch/pes13-nx/perf31-submit-diagnostics.txt","r");
    unsigned enabled=f ? fgetc(f)=='1' : 1;
    if(f) fclose(f);
    __atomic_store_n(&pes31_enabled,enabled,__ATOMIC_RELEASE);
    f=fopen("sdmc:/switch/pes13-nx/perf31-fence-poll.txt","r");
    unsigned poll=f ? fgetc(f)=='1' : 0;
    if(f) fclose(f);
    __atomic_store_n(&pes31_poll_enabled,poll,__ATOMIC_RELEASE);
}
static void pes31_report(void)
{
    static struct pes31_total previous[PES31_STAGES];
    unsigned enabled=__atomic_load_n(&pes31_enabled,__ATOMIC_RELAXED);
    log_line("[PERF31] submit_diagnostics=%u owners=%u owner_overflow=%u slow_event_drops=%u; nested host wall times, not GPU time",
        enabled,__atomic_load_n(&pes31_next_owner,__ATOMIC_RELAXED),
        __atomic_load_n(&pes31_owner_overflow,__ATOMIC_RELAXED),__atomic_load_n(&pes31_event_drops,__ATOMIC_RELAXED));
    log_line("[POLL31] enabled=%u error_scan_checked=%llu error_scan_deferred=%llu; cumulative; native fence query retained",
        wine_nx_perf31_poll_mode(),(unsigned long long)__atomic_load_n(&pes31_poll_checked,__ATOMIC_RELAXED),
        (unsigned long long)__atomic_load_n(&pes31_poll_deferred,__ATOMIC_RELAXED));
    if(!enabled) return;
    for(unsigned i=0;i<PES31_STAGES;++i) {
        struct pes31_total now={__atomic_load_n(&pes31_totals[i].calls,__ATOMIC_RELAXED),
            __atomic_load_n(&pes31_totals[i].ticks,__ATOMIC_RELAXED),
            __atomic_load_n(&pes31_totals[i].maximum,__ATOMIC_RELAXED),
            __atomic_load_n(&pes31_totals[i].slow,__ATOMIC_RELAXED)};
        uint64_t n=now.calls-previous[i].calls,ticks=now.ticks-previous[i].ticks;
        if(n) log_line("[STAGE31] %s n=%llu total_us=%llu gt100ms=%llu max_since_launch_us=%llu",
            pes31_names[i],(unsigned long long)n,(unsigned long long)pes31_to_us(ticks),
            (unsigned long long)(now.slow-previous[i].slow),(unsigned long long)pes31_to_us(now.maximum));
        previous[i]=now;
    }
    uint64_t now=pes31_clock();
    for(unsigned i=0;i<PES31_OWNERS;++i) {
        struct pes31_owner owner;
        if(!pes31_snapshot(i,&owner) || owner.stage>=PES31_STAGES || now<owner.start) continue;
        uint64_t age=pes31_to_us(now-owner.start);
        if(age>=100000) log_line("[ACTIVE31] owner_slot=%u handle=%x stage=%s object=%llx age_us=%llu",
            i,owner.handle,pes31_names[owner.stage],(unsigned long long)owner.object,(unsigned long long)age);
    }
    for(unsigned i=0;i<PES31_EVENTS;++i) {
        struct pes31_event *e=&pes31_events[i];
        if(__atomic_load_n(&e->state,__ATOMIC_ACQUIRE)!=2) continue;
        log_line("[SLOW31] handle=%x stage=%s object=%llx start_tick=%llu us=%llu",e->handle,pes31_names[e->stage],
            (unsigned long long)e->object,(unsigned long long)e->start,(unsigned long long)pes31_to_us(e->ticks));
        __atomic_store_n(&e->state,0,__ATOMIC_RELEASE);
    }
    static const char *value_names[PES31_VALUES]={"slm_warp","slm_tpc","image_pool","sampler_pool","audio_held","audio_submitted","audio_played"};
    for(unsigned i=0;i<PES31_VALUES;++i)
        log_line("[VALUE31] %s last=%llu max_since_launch=%llu",value_names[i],
            (unsigned long long)__atomic_load_n(&pes31_values[i],__ATOMIC_RELAXED),
            (unsigned long long)__atomic_load_n(&pes31_peaks[i],__ATOMIC_RELAXED));
}
