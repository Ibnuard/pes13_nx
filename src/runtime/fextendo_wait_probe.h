/* LGPL-2.1-or-later. Debug-only call progress, observed without pausing threads.
 * Producers never allocate, log, wait, dereference guest pointers or touch SD.
 * Each slot has one writer; generation checks reject stale completion tokens.
 * An entry without a return may also mean exception unwind, not necessarily a wait. */
#ifndef FEXTENDO_WAIT_PROBE_H
#define FEXTENDO_WAIT_PROBE_H
#include <stdint.h>
#include <string.h>
#define FX_WAIT_SLOTS 128
#define FX_WAIT_KINDS 3
#ifndef FX_WAIT_NOW
#define FX_WAIT_NOW() (armTicksToNs(armGetSystemTick())/1000000ull)
#endif
#ifndef FX_WAIT_THREAD
#define FX_WAIT_THREAD() threadGetCurHandle()
#endif
struct fx_wait_row {
    unsigned state,kind,code,thread,result;
    uint64_t begin,end,arg0,arg1;
};
static struct fx_wait_row fx_wait_rows[FX_WAIT_SLOTS];
static unsigned fx_wait_cursor;
static uint64_t fx_wait_started[FX_WAIT_KINDS],fx_wait_finished[FX_WAIT_KINDS],fx_wait_dropped;

/* Keep failed top-level NT calls after the ordinary recent-call slots have
 * been recycled by successful frame/audio traffic. This is diagnostic only:
 * statuses are never changed, and an API error is not necessarily fatal. */
#define FX_WAIT_ERRORS 64
struct fx_wait_error { struct fx_wait_row row; uint64_t serial; };
static struct fx_wait_error fx_wait_errors[FX_WAIT_ERRORS];
static uint64_t fx_wait_error_total,fx_wait_error_dropped;
static void fx_wait_error_record(const struct fx_wait_row *source)
{
    unsigned kind=__atomic_load_n(&source->kind,__ATOMIC_RELAXED);
    unsigned result=__atomic_load_n(&source->result,__ATOMIC_RELAXED);
    unsigned state,generation;
    uint64_t serial;
    struct fx_wait_error *error;
    /* Server-internal BAD_DEVICE_TYPE can deliberately route a pipe to its
     * native handler. Capture the public NT result, not that control flow. */
    if(kind!=0||(result&0xc0000000u)!=0xc0000000u)return;
    serial=__atomic_add_fetch(&fx_wait_error_total,1,__ATOMIC_RELAXED);
    error=&fx_wait_errors[(serial-1)%FX_WAIT_ERRORS];
    state=__atomic_load_n(&error->row.state,__ATOMIC_ACQUIRE);
    generation=(state+4)&~3u;if(!generation)generation=4;
    if((state&3)||!__atomic_compare_exchange_n(&error->row.state,&state,generation|2,0,
                                               __ATOMIC_ACQ_REL,__ATOMIC_RELAXED)){
        __atomic_add_fetch(&fx_wait_error_dropped,1,__ATOMIC_RELAXED);return;
    }
#define FX_ERROR_COPY(field) __atomic_store_n(&error->row.field,__atomic_load_n(&source->field,__ATOMIC_RELAXED),__ATOMIC_RELAXED)
    FX_ERROR_COPY(kind);FX_ERROR_COPY(code);FX_ERROR_COPY(thread);FX_ERROR_COPY(result);
    FX_ERROR_COPY(begin);FX_ERROR_COPY(end);FX_ERROR_COPY(arg0);FX_ERROR_COPY(arg1);
#undef FX_ERROR_COPY
    __atomic_store_n(&error->serial,serial,__ATOMIC_RELAXED);
    __atomic_store_n(&error->row.state,generation,__ATOMIC_RELEASE);
}
static int fx_wait_error_read(unsigned index,struct fx_wait_error *out)
{
    const struct fx_wait_error *error=&fx_wait_errors[index];
    unsigned state=__atomic_load_n(&error->row.state,__ATOMIC_ACQUIRE);
    if(!state||(state&3))return 0;
    out->row.state=state;
#define FX_ERROR_READ(field) out->row.field=__atomic_load_n(&error->row.field,__ATOMIC_RELAXED)
    FX_ERROR_READ(kind);FX_ERROR_READ(code);FX_ERROR_READ(thread);FX_ERROR_READ(result);
    FX_ERROR_READ(begin);FX_ERROR_READ(end);FX_ERROR_READ(arg0);FX_ERROR_READ(arg1);
#undef FX_ERROR_READ
    out->serial=__atomic_load_n(&error->serial,__ATOMIC_RELAXED);
    return state==__atomic_load_n(&error->row.state,__ATOMIC_ACQUIRE);
}

uint64_t wine_nx_wait_probe_begin(unsigned kind,unsigned code,uint64_t arg0,uint64_t arg1)
{
    unsigned start,i;
    if(!wine_nx_launch_debug_active()||kind>=FX_WAIT_KINDS)return 0;
    start=__atomic_fetch_add(&fx_wait_cursor,1,__ATOMIC_RELAXED);
    for(i=0;i<FX_WAIT_SLOTS;i++){
        unsigned index=(start+i)%FX_WAIT_SLOTS,state,generation;
        struct fx_wait_row *r=&fx_wait_rows[index];
        state=__atomic_load_n(&r->state,__ATOMIC_ACQUIRE);
        if(state&3)continue;
        generation=(state+4)&~3u;if(!generation)generation=4;
        if(!__atomic_compare_exchange_n(&r->state,&state,generation|2,0,__ATOMIC_ACQ_REL,__ATOMIC_RELAXED))continue;
        __atomic_store_n(&r->kind,kind,__ATOMIC_RELAXED);
        __atomic_store_n(&r->code,code,__ATOMIC_RELAXED);
        __atomic_store_n(&r->thread,FX_WAIT_THREAD(),__ATOMIC_RELAXED);
        __atomic_store_n(&r->begin,FX_WAIT_NOW(),__ATOMIC_RELAXED);
        __atomic_store_n(&r->end,0,__ATOMIC_RELAXED);
        __atomic_store_n(&r->arg0,arg0,__ATOMIC_RELAXED);
        __atomic_store_n(&r->arg1,arg1,__ATOMIC_RELAXED);
        __atomic_store_n(&r->result,0,__ATOMIC_RELAXED);
        __atomic_add_fetch(&fx_wait_started[kind],1,__ATOMIC_RELAXED);
        __atomic_store_n(&r->state,generation|1,__ATOMIC_RELEASE);
        return ((uint64_t)generation<<32)|(index+1);
    }
    __atomic_add_fetch(&fx_wait_dropped,1,__ATOMIC_RELAXED);
    return 0;
}

void wine_nx_wait_probe_end(uint64_t token,unsigned result)
{
    unsigned index=(unsigned)token,generation=(unsigned)(token>>32),expected;
    struct fx_wait_row *r;
    if(!index||index>FX_WAIT_SLOTS||!generation||(generation&3))return;
    r=&fx_wait_rows[index-1];expected=generation|1;
    if(!__atomic_compare_exchange_n(&r->state,&expected,generation|2,0,__ATOMIC_ACQ_REL,__ATOMIC_RELAXED))return;
    __atomic_store_n(&r->result,result,__ATOMIC_RELAXED);
    __atomic_store_n(&r->end,FX_WAIT_NOW(),__ATOMIC_RELAXED);
    fx_wait_error_record(r);
    __atomic_add_fetch(&fx_wait_finished[__atomic_load_n(&r->kind,__ATOMIC_RELAXED)],1,__ATOMIC_RELAXED);
    __atomic_store_n(&r->state,generation,__ATOMIC_RELEASE);
}

/* At most one read attempt; never spin behind a running producer. All fields
 * are atomic so even a rejected concurrent copy has no C data race. */
static int fx_wait_read(unsigned index,struct fx_wait_row *out)
{
    struct fx_wait_row *r=&fx_wait_rows[index];
    unsigned state=__atomic_load_n(&r->state,__ATOMIC_ACQUIRE);
    if(!state||(state&3)==2)return 0;
    out->state=state;
#define FX_WAIT_COPY(field) out->field=__atomic_load_n(&r->field,__ATOMIC_RELAXED)
    FX_WAIT_COPY(kind);FX_WAIT_COPY(code);FX_WAIT_COPY(thread);FX_WAIT_COPY(result);
    FX_WAIT_COPY(begin);FX_WAIT_COPY(end);FX_WAIT_COPY(arg0);FX_WAIT_COPY(arg1);
#undef FX_WAIT_COPY
    return state==__atomic_load_n(&r->state,__ATOMIC_ACQUIRE);
}

#ifndef FX_WAIT_NO_REPORT
static void fx_wait_error_report(void)
{
    static uint64_t seen[FX_WAIT_ERRORS],previous_total;
    struct fx_wait_error error;
    unsigned shown=0,omitted=0;
    uint64_t total=__atomic_load_n(&fx_wait_error_total,__ATOMIC_RELAXED);
    /* A producer reserves its serial before publishing the row. Still scan
     * when the count is unchanged so a snapshot racing publication retries
     * that completed record on the next maintenance tick. */
    for(unsigned i=0;i<FX_WAIT_ERRORS;i++){
        if(!fx_wait_error_read(i,&error)||seen[i]==error.serial)continue;
        seen[i]=error.serial;
        if(shown++>=32){omitted++;continue;}
        fx_launch_debug_log("[WAIT-ERROR] seq=%llu nt=%x thread=%x status=%08x end_ms=%llu arg0=%llx arg1=%llx; API failure, not necessarily fatal",
            (unsigned long long)error.serial,error.row.code,error.row.thread,error.row.result,
            (unsigned long long)error.row.end,(unsigned long long)error.row.arg0,
            (unsigned long long)error.row.arg1);
    }
    if(!shown&&total==previous_total)return;
    fx_launch_debug_log("[WAIT-ERRORS] total=%llu delta=%llu producer_drop=%llu report_omitted=%u retained=%u",
        (unsigned long long)total,(unsigned long long)(total-previous_total),
        (unsigned long long)__atomic_load_n(&fx_wait_error_dropped,__ATOMIC_RELAXED),omitted,FX_WAIT_ERRORS);
    previous_total=total;
}
/* Read counters already maintained by Wine; no additional producer hooks.
 * Recent results sample the reusable slots; they are not a call-rate estimate. */
static void __attribute__((noinline)) fx_wait_call_summary(uint64_t now)
{
    extern unsigned wine_nx_syscall_counts[0x2000] __attribute__((weak));
    extern unsigned wine_nx_server_request_count __attribute__((weak));
    extern unsigned wine_nx_server_calls[] __attribute__((weak));
    static unsigned previous_nt[0x2000],previous_server[1024];
    static const char *const names[FX_WAIT_KINDS]={"nt","server","vulkan"};
    struct {unsigned kind,code,thread,result,count;uint64_t arg0,arg1;} samples[FX_WAIT_SLOTS];
    unsigned count=0;
    struct fx_wait_row r;
    for(unsigned k=0;k<2;k++){
        unsigned *counters=k?wine_nx_server_calls:wine_nx_syscall_counts;
        unsigned *prev=k?previous_server:previous_nt;
        unsigned length=k?(&wine_nx_server_request_count?wine_nx_server_request_count:0):0x2000;
        struct {unsigned code,calls;} top[3]={{0}};
        if(!counters)continue;
        if(k&&length>1024)length=1024;
        for(unsigned i=0;i<length;i++){
            unsigned current=__atomic_load_n(&counters[i],__ATOMIC_RELAXED),delta=current-prev[i];
            prev[i]=current;
            for(unsigned j=0;j<3;j++)if(delta>top[j].calls){
                for(unsigned n=2;n>j;n--)top[n]=top[n-1];
                top[j].code=i;top[j].calls=delta;break;
            }
        }
        for(unsigned j=0;j<3;j++)if(top[j].calls)
            fx_launch_debug_log("[WAIT-HOT] kind=%s code=%x calls=%u",names[k],top[j].code,top[j].calls);
    }
    for(unsigned i=0;i<FX_WAIT_SLOTS;i++){
        unsigned j;
        if(!fx_wait_read(i,&r)||(r.state&3)||r.kind>=FX_WAIT_KINDS||!r.end||now<r.end||now-r.end>1000)continue;
        for(j=0;j<count;j++)if(samples[j].kind==r.kind&&samples[j].code==r.code&&
            samples[j].thread==r.thread&&samples[j].result==r.result)break;
        if(j==count){
            samples[j].kind=r.kind;samples[j].code=r.code;samples[j].thread=r.thread;
            samples[j].result=r.result;samples[j].count=0;count++;
        }
        samples[j].count++;samples[j].arg0=r.arg0;samples[j].arg1=r.arg1;
    }
    for(unsigned n=0;n<8&&n<count;n++){
        unsigned best=0;
        for(unsigned i=1;i<count;i++)if(samples[i].count>samples[best].count)best=i;
        if(!samples[best].count)break;
        fx_launch_debug_log("[WAIT-RECENT] kind=%s code=%x thread=%x status=%08x samples=%u arg0=%llx arg1=%llx",
            names[samples[best].kind],samples[best].code,samples[best].thread,samples[best].result,
            samples[best].count,(unsigned long long)samples[best].arg0,(unsigned long long)samples[best].arg1);
        samples[best].count=0;
    }
}

static void fx_wait_probe_tick(void)
{
    extern unsigned wine_nx_vk_presents __attribute__((weak));
    extern void wine_nx_wait_probe_threads(void);
    static unsigned previous,ready;
    static uint64_t progress;
    static const char *const names[FX_WAIT_KINDS]={"nt","server","vulkan"};
    struct fx_wait_row r;
    unsigned presents,active=0,shown=0;
    uint64_t now;
    if(!wine_nx_launch_debug_active())return;
    now=FX_WAIT_NOW();
    presents=&wine_nx_vk_presents?__atomic_load_n(&wine_nx_vk_presents,__ATOMIC_RELAXED):0;
    if(!ready||presents!=previous){progress=now;ready=1;}
    fx_launch_debug_log("[WAIT-PROBE] presents=%u delta=%u idle_ms=%llu dropped=%llu",
        presents,presents-previous,(unsigned long long)(now>=progress?now-progress:0),
        (unsigned long long)__atomic_load_n(&fx_wait_dropped,__ATOMIC_RELAXED));
    previous=presents;
    for(unsigned k=0;k<FX_WAIT_KINDS;k++)
        fx_launch_debug_log("[WAIT-CALLS] kind=%s enter=%llu return=%llu",names[k],
            (unsigned long long)__atomic_load_n(&fx_wait_started[k],__ATOMIC_RELAXED),
            (unsigned long long)__atomic_load_n(&fx_wait_finished[k],__ATOMIC_RELAXED));
    for(unsigned i=0;i<FX_WAIT_SLOTS;i++){
        if(!fx_wait_read(i,&r)||!(r.state&1)||r.kind>=FX_WAIT_KINDS)continue;
        active++;
        if(now<r.begin||now-r.begin<1000||shown==24)continue;
        shown++;
        fx_launch_debug_log("[WAIT-INFLIGHT] kind=%s code=%x thread=%x age_ms=%llu arg0=%llx arg1=%llx",
            names[r.kind],r.code,r.thread,(unsigned long long)(now-r.begin),
            (unsigned long long)r.arg0,(unsigned long long)r.arg1);
    }
    fx_launch_debug_log("[WAIT-PROBE] active=%u shown=%u; entry without return can include unwind",active,shown);
    fx_wait_call_summary(now);
    fx_wait_error_report();
    wine_nx_wait_probe_threads();
}
#endif
#endif
