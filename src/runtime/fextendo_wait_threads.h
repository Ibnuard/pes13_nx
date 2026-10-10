/* LGPL-2.1-or-later. Include after thread_profile.c. No suspension, stack
 * walking or guest memory reads. Try-lock protects registered handle lifetime. */
void wine_nx_wait_probe_threads(void)
{
    extern int wine_nx_launch_debug_active(void);
    static struct {Handle handle;u64 ticks;} previous[NX_PROF_MAX_THREADS];
    static u64 last_time;
    struct {Handle handle;unsigned tid;char kind;u64 ticks;unsigned valid;} rows[NX_PROF_MAX_THREADS];
    unsigned count=0;
    u64 now,interval;
    char line[192];
    if(!wine_nx_launch_debug_active())return;
    if(pthread_mutex_trylock(&registry_mutex)){
        wine_nx_runtime_trace("[WAIT-CPU] registry busy; skipped");return;
    }
    now=armGetSystemTick();interval=last_time&&now>=last_time?now-last_time:0;
    for(unsigned i=0;i<NX_PROF_MAX_THREADS;i++){
        u64 ticks=0;Result rc;
        if(!registry[i].handle){previous[i].handle=0;continue;}
        rc=svcGetInfo(&ticks,InfoType_ThreadTickCount,registry[i].handle,UINT64_MAX);
        if(R_FAILED(rc))rc=svcGetInfo(&ticks,InfoType_ThreadTickCountDeprecated,registry[i].handle,UINT64_MAX);
        unsigned valid=R_SUCCEEDED(rc)&&interval&&previous[i].handle==registry[i].handle&&ticks>=previous[i].ticks;
        rows[count].handle=registry[i].handle;rows[count].tid=registry[i].tid;rows[count].kind=registry[i].kind;
        rows[count].ticks=valid?ticks-previous[i].ticks:0;rows[count++].valid=valid;
        previous[i].handle=R_SUCCEEDED(rc)?registry[i].handle:0;previous[i].ticks=ticks;
    }
    last_time=now;
    pthread_mutex_unlock(&registry_mutex);
    /* Main plus the seven busiest measured threads, after releasing registry. */
    for(unsigned n=0;n<8&&n<count;n++){
        unsigned selected=NX_PROF_MAX_THREADS;
        for(unsigned i=0;i<count;i++){
            if(!rows[i].handle)continue;
            if(n==0&&rows[i].kind=='w'&&rows[i].tid==4){selected=i;break;}
            if(selected==NX_PROF_MAX_THREADS||rows[i].ticks>rows[selected].ticks)selected=i;
        }
        if(selected==NX_PROF_MAX_THREADS)break;
        snprintf(line,sizeof(line),"[WAIT-CPU] tid=%u%c thread=%x valid=%u cpu_ms=%llu interval_ms=%llu",
            rows[selected].tid,rows[selected].kind,rows[selected].handle,rows[selected].valid,
            (unsigned long long)(armTicksToNs(rows[selected].ticks)/1000000),
            (unsigned long long)(armTicksToNs(interval)/1000000));
        wine_nx_runtime_trace(line);rows[selected].handle=0;
    }
}
