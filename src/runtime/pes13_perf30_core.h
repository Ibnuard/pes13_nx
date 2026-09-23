/* One owning thread per slot. Report readers never pause, lock or dereference
 * the observed objects. Slots persist until process exit; overflow is counted. */
#ifndef PES13_PERF30_CORE_H
#define PES13_PERF30_CORE_H
#include "pes13_perf30.h"
#define PES30_OWNERS 64
#define PES30_EVENTS 16
struct pes30_owner { uint64_t sequence,start; uintptr_t object; unsigned stage,handle; };
struct pes30_total { uint64_t calls,ticks,maximum,slow; };
struct pes30_event { unsigned state,stage,handle; uintptr_t object; uint64_t start,ticks; };
static struct pes30_owner pes30_owners[PES30_OWNERS];
static struct pes30_total pes30_totals[PES30_STAGES];
static struct pes30_event pes30_events[PES30_EVENTS];
static uint64_t pes30_values[PES30_VALUES],pes30_peaks[PES30_VALUES];
static unsigned pes30_enabled,pes30_next_owner,pes30_owner_overflow,pes30_event_drops;
static __thread unsigned pes30_owner_slot;
/* Supplied by runtime or host test, in 19.2MHz ticks on Switch. */
static uint64_t pes30_clock(void);
static unsigned pes30_handle(void);
static uint64_t pes30_to_us(uint64_t ticks);
static void pes30_max(uint64_t *dst,uint64_t value)
{
    uint64_t old=__atomic_load_n(dst,__ATOMIC_RELAXED);
    while(old<value && !__atomic_compare_exchange_n(dst,&old,value,1,__ATOMIC_RELAXED,__ATOMIC_RELAXED)) {}
}
static void pes30_publish(struct pes30_owner *o,unsigned stage,uintptr_t object,uint64_t start)
{
    /* All fields atomic so a concurrent failed snapshot remains data-race free. */
    __atomic_add_fetch(&o->sequence,1,__ATOMIC_SEQ_CST);
    __atomic_store_n(&o->stage,stage,__ATOMIC_SEQ_CST);
    __atomic_store_n(&o->object,object,__ATOMIC_SEQ_CST);
    __atomic_store_n(&o->start,start,__ATOMIC_SEQ_CST);
    __atomic_add_fetch(&o->sequence,1,__ATOMIC_SEQ_CST);
}
struct pes30_token wine_nx_perf30_enter(unsigned stage,uintptr_t object)
{
    struct pes30_token t={0};
    if(stage>=PES30_STAGES || !__atomic_load_n(&pes30_enabled,__ATOMIC_RELAXED)) return t;
    t.start=pes30_clock();t.stage=stage;t.object=object;
    if(!pes30_owner_slot) {
        unsigned n=__atomic_fetch_add(&pes30_next_owner,1,__ATOMIC_RELAXED);
        pes30_owner_slot=n<PES30_OWNERS ? n+1 : PES30_OWNERS+1;
        if(n<PES30_OWNERS) {
            __atomic_store_n(&pes30_owners[n].handle,pes30_handle(),__ATOMIC_RELEASE);
            pes30_publish(&pes30_owners[n],PES30_STAGES,0,0);
        } else __atomic_add_fetch(&pes30_owner_overflow,1,__ATOMIC_RELAXED);
    }
    t.slot=pes30_owner_slot;
    if(t.slot<=PES30_OWNERS) {
        struct pes30_owner *o=&pes30_owners[t.slot-1];
        t.previous_stage=__atomic_load_n(&o->stage,__ATOMIC_RELAXED);
        t.previous_object=__atomic_load_n(&o->object,__ATOMIC_RELAXED);
        t.previous_start=__atomic_load_n(&o->start,__ATOMIC_RELAXED);
        pes30_publish(o,stage,object,t.start);
    }
    return t;
}
void wine_nx_perf30_leave(struct pes30_token t)
{
    if(!t.slot) return;
    uint64_t ticks=pes30_clock()-t.start;
    struct pes30_total *v=&pes30_totals[t.stage];
    __atomic_add_fetch(&v->calls,1,__ATOMIC_RELAXED);
    __atomic_add_fetch(&v->ticks,ticks,__ATOMIC_RELAXED);pes30_max(&v->maximum,ticks);
    if(t.slot<=PES30_OWNERS) pes30_publish(&pes30_owners[t.slot-1],t.previous_stage,t.previous_object,t.previous_start);
    if(pes30_to_us(ticks)<100000) return;
    __atomic_add_fetch(&v->slow,1,__ATOMIC_RELAXED);
    for(unsigned i=0;i<PES30_EVENTS;++i) {
        unsigned free=0;
        if(!__atomic_compare_exchange_n(&pes30_events[i].state,&free,1,0,__ATOMIC_ACQUIRE,__ATOMIC_RELAXED)) continue;
        struct pes30_event *e=&pes30_events[i];
        e->stage=t.stage;e->handle=pes30_handle();e->object=t.object;e->start=t.start;e->ticks=ticks;
        __atomic_store_n(&e->state,2,__ATOMIC_RELEASE);return;
    }
    __atomic_add_fetch(&pes30_event_drops,1,__ATOMIC_RELAXED);
}
void wine_nx_perf30_value(unsigned index,uint64_t value)
{
    if(index>=PES30_VALUES || !__atomic_load_n(&pes30_enabled,__ATOMIC_RELAXED)) return;
    __atomic_store_n(&pes30_values[index],value,__ATOMIC_RELAXED);pes30_max(&pes30_peaks[index],value);
}
static int pes30_snapshot(unsigned n,struct pes30_owner *out)
{
    if(n>=PES30_OWNERS) return 0;
    const struct pes30_owner *o=&pes30_owners[n];
    uint64_t seq=__atomic_load_n(&o->sequence,__ATOMIC_SEQ_CST);
    if(!seq || (seq&1)) return 0;
    out->handle=__atomic_load_n(&o->handle,__ATOMIC_ACQUIRE);
    out->stage=__atomic_load_n(&o->stage,__ATOMIC_SEQ_CST);
    out->object=__atomic_load_n(&o->object,__ATOMIC_SEQ_CST);
    out->start=__atomic_load_n(&o->start,__ATOMIC_SEQ_CST);
    return seq==__atomic_load_n(&o->sequence,__ATOMIC_SEQ_CST);
}
#endif
