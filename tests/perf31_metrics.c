#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include "../src/runtime/pes13_perf31_core.h"
static __thread uint64_t fake_time;
static uint64_t pes31_clock(void) { return fake_time; }
static uint64_t pes31_to_us(uint64_t ticks) { return ticks; }
static unsigned pes31_handle(void) { return 123; }
static unsigned finished;
static void *writer(void *arg)
{
    (void)arg;
    for(unsigned i=0;i<10000;++i) {
        struct pes31_token outer=wine_nx_perf31_enter(PES31_COMMANDS,99);
        fake_time+=2;
        struct pes31_token inner=wine_nx_perf31_enter(PES31_KICKOFF,88);
        fake_time+=3;wine_nx_perf31_leave(inner);
        fake_time+=5;wine_nx_perf31_leave(outer);
    }
    __atomic_add_fetch(&finished,1,__ATOMIC_RELEASE);return NULL;
}
int main(void)
{
    struct pes31_token t=wine_nx_perf31_enter(PES31_COMMANDS,1);
    assert(!t.slot);wine_nx_perf31_leave(t);assert(!pes31_next_owner);
    pes31_enabled=1;assert(!wine_nx_perf31_enter(PES31_STAGES,1).slot);
    t=wine_nx_perf31_enter(PES31_COMMANDS,1);fake_time=7;
    struct pes31_token inner=wine_nx_perf31_enter(PES31_KICKOFF,2);
    struct pes31_owner out;assert(pes31_snapshot(t.slot-1,&out) && out.object==2 && out.start==7);
    fake_time=17;wine_nx_perf31_leave(inner);
    assert(pes31_snapshot(t.slot-1,&out) && out.object==1 && out.start==0);
    fake_time=30;wine_nx_perf31_leave(t);
    assert(pes31_snapshot(t.slot-1,&out) && out.stage==PES31_STAGES);
    assert(pes31_totals[PES31_COMMANDS].ticks==30 && pes31_totals[PES31_KICKOFF].ticks==10);
    pthread_t threads[8];
    for(unsigned i=0;i<8;++i) assert(!pthread_create(&threads[i],NULL,writer,NULL));
    while(__atomic_load_n(&finished,__ATOMIC_ACQUIRE)<8) for(unsigned i=1;i<9;++i) {
        if(pes31_snapshot(i,&out) && out.stage<PES31_STAGES)
            assert((out.stage==PES31_COMMANDS && out.object==99) || (out.stage==PES31_KICKOFF && out.object==88));
    }
    for(unsigned i=0;i<8;++i) assert(!pthread_join(threads[i],NULL));
    assert(pes31_totals[PES31_COMMANDS].calls==80001 && pes31_totals[PES31_COMMANDS].ticks==800030);
    assert(pes31_totals[PES31_KICKOFF].calls==80001 && pes31_totals[PES31_KICKOFF].ticks==240010);
    for(unsigned i=0;i<PES31_EVENTS+3;++i) {
        t=wine_nx_perf31_enter(PES31_CHANNEL_SUBMIT,4);fake_time+=100000;wine_nx_perf31_leave(t);
    }
    assert(pes31_event_drops==3 && pes31_totals[PES31_CHANNEL_SUBMIT].slow==PES31_EVENTS+3);
    for(unsigned i=0;i<PES31_EVENTS;++i) {
        assert(pes31_events[i].state==2 && pes31_events[i].ticks==100000);pes31_events[i].state=0;
    }
    pes31_owner_slot=PES31_OWNERS+1;
    t=wine_nx_perf31_enter(PES31_SIGNAL,5);fake_time+=9;wine_nx_perf31_leave(t);
    assert(pes31_totals[PES31_SIGNAL].ticks==9);
    wine_nx_perf31_value(PES31_SLM_WARP,10);wine_nx_perf31_value(PES31_SLM_WARP,3);
    assert(pes31_values[PES31_SLM_WARP]==3 && pes31_peaks[PES31_SLM_WARP]==10);
    pes31_enabled=0;wine_nx_perf31_value(PES31_SLM_WARP,22);assert(pes31_values[PES31_SLM_WARP]==3);
    puts("PERF31 nested spans, disabled path, concurrent coherent snapshots/totals, bounded slow events and gauges PASS");
}
