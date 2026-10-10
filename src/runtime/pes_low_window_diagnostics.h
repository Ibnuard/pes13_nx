/* LGPL-2.1-or-later. Existing counters only; no new hot-path probes, guest
 * writes, timer scaling, thread suspension or SD writes in this reader.
 * The production maintenance thread queues these reports only in Debug. */
static void fx_low_window_io_report(void)
{
    extern unsigned int wine_nx_sd_reads, wine_nx_sd_hits;
    extern unsigned long long wine_nx_sd_read_ns;
    static unsigned previous_reads, previous_hits;
    static uint64_t previous_ns, previous_tick;
    unsigned reads=__atomic_load_n(&wine_nx_sd_reads,__ATOMIC_RELAXED);
    unsigned hits=__atomic_load_n(&wine_nx_sd_hits,__ATOMIC_RELAXED);
    uint64_t ns=__atomic_load_n(&wine_nx_sd_read_ns,__ATOMIC_RELAXED);
    uint64_t now=armGetSystemTick();
    log_line("[LW2-IO] window_ms=%llu reads=%u cache_hits=%u fs_read_us=%llu; summed completed read wall time, may overlap",
             (unsigned long long)(previous_tick&&now>=previous_tick?armTicksToNs(now-previous_tick)/1000000:0),
             reads-previous_reads,hits-previous_hits,(unsigned long long)((ns-previous_ns)/1000));
    previous_reads=reads;previous_hits=hits;previous_ns=ns;previous_tick=now;
}

static void __attribute__((noinline)) fx_low_window_diagnostics(unsigned ticks)
{
    if(!wine_nx_launch_debug_active())return;
    if(ticks%25==0)fex_game_timing_report();
    if(ticks%50==0){
        fex_frame_report();
        fex_pipeline_report();
        fex_warm_report();
        fx_low_window_io_report();
    }
}
