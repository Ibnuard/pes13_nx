/* One owning thread per slot. Report readers never pause, lock or dereference
 * the observed objects. Slots persist until process exit; overflow is counted. */
#ifndef PES13_PERF31_CORE_H
#define PES13_PERF31_CORE_H
#include "pes13_perf31.h"
#define PES31_OWNERS 64
#define PES31_EVENTS 16
struct pes31_owner { uint64_t sequence,start; uintptr_t object; unsigned stage,handle; };
struct pes31_total { uint64_t calls,ticks,maximum,slow; };
struct pes31_event { unsigned state,stage,handle; uintptr_t object; uint64_t start,ticks; };
static struct pes31_owner pes31_owners[PES31_OWNERS];
static struct pes31_total pes31_totals[PES31_STAGES];
static struct pes31_event pes31_events[PES31_EVENTS];
static uint64_t pes31_values[PES31_VALUES],pes31_peaks[PES31_VALUES];
static unsigned pes31_enabled,pes31_next_owner,pes31_owner_overflow,pes31_event_drops;
static __thread unsigned pes31_owner_slot;
/* Supplied by runtime or host test, in 19.2MHz ticks on Switch. */
static uint64_t pes31_clock(void);
static unsigned pes31_handle(void);
static uint64_t pes31_to_us(uint64_t ticks);
static void pes31_max(uint64_t *dst,uint64_t value)
{
    uint64_t old=__atomic_load_n(dst,__ATOMIC_RELAXED);
    while(old<value && !__atomic_compare_exchange_n(dst,&old,value,1,__ATOMIC_RELAXED,__ATOMIC_RELAXED)) {}
}
static void pes31_publish(struct pes31_owner *o,unsigned stage,uintptr_t object,uint64_t start)
{
    /* All fields atomic so a concurrent failed snapshot remains data-race free. */
    __atomic_add_fetch(&o->sequence,1,__ATOMIC_SEQ_CST);
    __atomic_store_n(&o->stage,stage,__ATOMIC_SEQ_CST);
    __atomic_store_n(&o->object,object,__ATOMIC_SEQ_CST);
    __atomic_store_n(&o->start,start,__ATOMIC_SEQ_CST);
    __atomic_add_fetch(&o->sequence,1,__ATOMIC_SEQ_CST);
}
struct pes31_token wine_nx_perf31_enter(unsigned stage,uintptr_t object)
{
    struct pes31_token t={0};
    if(stage>=PES31_STAGES || !__atomic_load_n(&pes31_enabled,__ATOMIC_RELAXED)) return t;
    t.start=pes31_clock();t.stage=stage;t.object=object;
    if(!pes31_owner_slot) {
        unsigned n=__atomic_fetch_add(&pes31_next_owner,1,__ATOMIC_RELAXED);
        pes31_owner_slot=n<PES31_OWNERS ? n+1 : PES31_OWNERS+1;
        if(n<PES31_OWNERS) {
            __atomic_store_n(&pes31_owners[n].handle,pes31_handle(),__ATOMIC_RELEASE);
            pes31_publish(&pes31_owners[n],PES31_STAGES,0,0);
        } else __atomic_add_fetch(&pes31_owner_overflow,1,__ATOMIC_RELAXED);
    }
    t.slot=pes31_owner_slot;
    if(t.slot<=PES31_OWNERS) {
        struct pes31_owner *o=&pes31_owners[t.slot-1];
        t.previous_stage=__atomic_load_n(&o->stage,__ATOMIC_RELAXED);
        t.previous_object=__atomic_load_n(&o->object,__ATOMIC_RELAXED);
        t.previous_start=__atomic_load_n(&o->start,__ATOMIC_RELAXED);
        pes31_publish(o,stage,object,t.start);
    }
    return t;
}
void wine_nx_perf31_leave(struct pes31_token t)
{
    if(!t.slot) return;
    uint64_t ticks=pes31_clock()-t.start;
    struct pes31_total *v=&pes31_totals[t.stage];
    __atomic_add_fetch(&v->calls,1,__ATOMIC_RELAXED);
    __atomic_add_fetch(&v->ticks,ticks,__ATOMIC_RELAXED);pes31_max(&v->maximum,ticks);
    if(t.slot<=PES31_OWNERS) pes31_publish(&pes31_owners[t.slot-1],t.previous_stage,t.previous_object,t.previous_start);
    if(pes31_to_us(ticks)<100000) return;
    __atomic_add_fetch(&v->slow,1,__ATOMIC_RELAXED);
    for(unsigned i=0;i<PES31_EVENTS;++i) {
        unsigned free=0;
        if(!__atomic_compare_exchange_n(&pes31_events[i].state,&free,1,0,__ATOMIC_ACQUIRE,__ATOMIC_RELAXED)) continue;
        struct pes31_event *e=&pes31_events[i];
        e->stage=t.stage;e->handle=pes31_handle();e->object=t.object;e->start=t.start;e->ticks=ticks;
        __atomic_store_n(&e->state,2,__ATOMIC_RELEASE);return;
    }
    __atomic_add_fetch(&pes31_event_drops,1,__ATOMIC_RELAXED);
}
void wine_nx_perf31_value(unsigned index,uint64_t value)
{
    if(index>=PES31_VALUES || !__atomic_load_n(&pes31_enabled,__ATOMIC_RELAXED)) return;
    __atomic_store_n(&pes31_values[index],value,__ATOMIC_RELAXED);pes31_max(&pes31_peaks[index],value);
}
static int pes31_snapshot(unsigned n,struct pes31_owner *out)
{
    if(n>=PES31_OWNERS) return 0;
    const struct pes31_owner *o=&pes31_owners[n];
    uint64_t seq=__atomic_load_n(&o->sequence,__ATOMIC_SEQ_CST);
    if(!seq || (seq&1)) return 0;
    out->handle=__atomic_load_n(&o->handle,__ATOMIC_ACQUIRE);
    out->stage=__atomic_load_n(&o->stage,__ATOMIC_SEQ_CST);
    out->object=__atomic_load_n(&o->object,__ATOMIC_SEQ_CST);
    out->start=__atomic_load_n(&o->start,__ATOMIC_SEQ_CST);
    return seq==__atomic_load_n(&o->sequence,__ATOMIC_SEQ_CST);
}
#endif
