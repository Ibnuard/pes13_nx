#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include "../src/runtime/pes13_perf30_core.h"
static __thread uint64_t fake_time;
static uint64_t pes30_clock(void) { return fake_time; }
static uint64_t pes30_to_us(uint64_t ticks) { return ticks; }
static unsigned pes30_handle(void) { return 123; }
static unsigned finished;
static void *writer(void *arg)
{
    (void)arg;
    for(unsigned i=0;i<10000;++i) {
        struct pes30_token outer=wine_nx_perf30_enter(PES30_COMMANDS,99);
        fake_time+=2;
        struct pes30_token inner=wine_nx_perf30_enter(PES30_KICKOFF,88);
        fake_time+=3;wine_nx_perf30_leave(inner);
        fake_time+=5;wine_nx_perf30_leave(outer);
    }
    __atomic_add_fetch(&finished,1,__ATOMIC_RELEASE);return NULL;
}
int main(void)
{
    struct pes30_token t=wine_nx_perf30_enter(PES30_COMMANDS,1);
    assert(!t.slot);wine_nx_perf30_leave(t);assert(!pes30_next_owner);
    pes30_enabled=1;assert(!wine_nx_perf30_enter(PES30_STAGES,1).slot);
    t=wine_nx_perf30_enter(PES30_COMMANDS,1);fake_time=7;
    struct pes30_token inner=wine_nx_perf30_enter(PES30_KICKOFF,2);
    struct pes30_owner out;assert(pes30_snapshot(t.slot-1,&out) && out.object==2 && out.start==7);
    fake_time=17;wine_nx_perf30_leave(inner);
    assert(pes30_snapshot(t.slot-1,&out) && out.object==1 && out.start==0);
    fake_time=30;wine_nx_perf30_leave(t);
    assert(pes30_snapshot(t.slot-1,&out) && out.stage==PES30_STAGES);
    assert(pes30_totals[PES30_COMMANDS].ticks==30 && pes30_totals[PES30_KICKOFF].ticks==10);
    pthread_t threads[8];
    for(unsigned i=0;i<8;++i) assert(!pthread_create(&threads[i],NULL,writer,NULL));
    while(__atomic_load_n(&finished,__ATOMIC_ACQUIRE)<8) for(unsigned i=1;i<9;++i) {
        if(pes30_snapshot(i,&out) && out.stage<PES30_STAGES)
            assert((out.stage==PES30_COMMANDS && out.object==99) || (out.stage==PES30_KICKOFF && out.object==88));
    }
    for(unsigned i=0;i<8;++i) assert(!pthread_join(threads[i],NULL));
    assert(pes30_totals[PES30_COMMANDS].calls==80001 && pes30_totals[PES30_COMMANDS].ticks==800030);
    assert(pes30_totals[PES30_KICKOFF].calls==80001 && pes30_totals[PES30_KICKOFF].ticks==240010);
    for(unsigned i=0;i<PES30_EVENTS+3;++i) {
        t=wine_nx_perf30_enter(PES30_CHANNEL_SUBMIT,4);fake_time+=100000;wine_nx_perf30_leave(t);
    }
    assert(pes30_event_drops==3 && pes30_totals[PES30_CHANNEL_SUBMIT].slow==PES30_EVENTS+3);
    for(unsigned i=0;i<PES30_EVENTS;++i) {
        assert(pes30_events[i].state==2 && pes30_events[i].ticks==100000);pes30_events[i].state=0;
    }
    pes30_owner_slot=PES30_OWNERS+1;
    t=wine_nx_perf30_enter(PES30_SIGNAL,5);fake_time+=9;wine_nx_perf30_leave(t);
    assert(pes30_totals[PES30_SIGNAL].ticks==9);
    wine_nx_perf30_value(PES30_SLM_WARP,10);wine_nx_perf30_value(PES30_SLM_WARP,3);
    assert(pes30_values[PES30_SLM_WARP]==3 && pes30_peaks[PES30_SLM_WARP]==10);
    pes30_enabled=0;wine_nx_perf30_value(PES30_SLM_WARP,22);assert(pes30_values[PES30_SLM_WARP]==3);
    puts("PERF30 nested spans, disabled path, concurrent coherent snapshots/totals, bounded slow events and gauges PASS");
}
