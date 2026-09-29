/* LGPL-2.1-or-later. Short-stall diagnostics: fixed storage, try-lock only on
 * producers, no SD I/O/allocations/thread suspension on observed paths. */
#define FEX_SHORT_ROWS 256
#define FEX_SHORT_TEXT 128
#define FEX_SHORT_BYTES 512
#define FEX_SHORT_WAIT_SLOTS 128
static int fex_short_enabled;
struct fex_short_row {
    uint64_t begin,end,object,wake_tick;
    unsigned kind,tid,handle,result,waker,wakes,wake_result;
};
static struct {
    pthread_mutex_t mutex;
    struct fex_short_row rows[FEX_SHORT_ROWS];
    unsigned head,count;
    uint64_t dropped,queued;
} fex_short_queue={.mutex=PTHREAD_MUTEX_INITIALIZER};
static struct {
    pthread_mutex_t mutex;
    char rows[FEX_SHORT_TEXT][FEX_SHORT_BYTES];
    unsigned head,count;
    uint64_t dropped,queued;
} fex_short_text={.mutex=PTHREAD_MUTEX_INITIALIZER};
struct fex_short_wait_slot {
    unsigned busy,tid,waker,wakes,wake_result;
    uint64_t live,generation;
    uint64_t begin,wake_tick;
};
static struct fex_short_wait_slot fex_short_waits[FEX_SHORT_WAIT_SLOTS];
static uint64_t fex_short_wait_lost, fex_short_generation;
static __thread uint64_t fex_short_wait_token;
static void fex_short_push(struct fex_short_row row) {
    if(!__atomic_load_n(&fex_short_enabled,__ATOMIC_ACQUIRE))return;
    if(pthread_mutex_trylock(&fex_short_queue.mutex)){
        __atomic_add_fetch(&fex_short_queue.dropped,1,__ATOMIC_RELAXED);return;
    }
    if(fex_short_queue.count==FEX_SHORT_ROWS)__atomic_add_fetch(&fex_short_queue.dropped,1,__ATOMIC_RELAXED);
    else{
        fex_short_queue.rows[(fex_short_queue.head+fex_short_queue.count++)%FEX_SHORT_ROWS]=row;
        __atomic_add_fetch(&fex_short_queue.queued,1,__ATOMIC_RELAXED);
    }
    pthread_mutex_unlock(&fex_short_queue.mutex);
}
/* Consume trace prefixes even OFF/overflow: never fall back to synchronous SD. */
static int fex_short_enqueue_text(const char *text) {
    if(strncmp(text,"[FEX3-JIT-THREAD] ",sizeof("[FEX3-JIT-THREAD] ")-1)&&
       strncmp(text,"[FEX3-COMPILE] ",sizeof("[FEX3-COMPILE] ")-1)&&
       strncmp(text,"[FEX3-BLOCK] ",sizeof("[FEX3-BLOCK] ")-1)&&
       strncmp(text,"[FEX3-JIT-SLOW] ",sizeof("[FEX3-JIT-SLOW] ")-1)&&
       strncmp(text,"[FEX3-JIT-CLOCK] ",sizeof("[FEX3-JIT-CLOCK] ")-1))return 0;
    if(!__atomic_load_n(&fex_short_enabled,__ATOMIC_ACQUIRE))return 1;
    size_t n=strnlen(text,FEX_SHORT_BYTES);
    if(n==FEX_SHORT_BYTES||pthread_mutex_trylock(&fex_short_text.mutex)){
        __atomic_add_fetch(&fex_short_text.dropped,1,__ATOMIC_RELAXED);return 1;
    }
    if(fex_short_text.count==FEX_SHORT_TEXT)__atomic_add_fetch(&fex_short_text.dropped,1,__ATOMIC_RELAXED);
    else{
        memcpy(fex_short_text.rows[(fex_short_text.head+fex_short_text.count++)%FEX_SHORT_TEXT],text,n+1);
        __atomic_add_fetch(&fex_short_text.queued,1,__ATOMIC_RELAXED);
    }
    pthread_mutex_unlock(&fex_short_text.mutex);return 1;
}
static unsigned fex_short_tid(void) {
    TEB *teb=NtCurrentTeb();return teb?(unsigned)(uintptr_t)teb->ClientId.UniqueThread:0;
}
uint64_t wine_nx_fex_short_begin(void) {
    return __atomic_load_n(&fex_short_enabled,__ATOMIC_ACQUIRE)?armGetSystemTick():0;
}
void wine_nx_fex_short_stage(unsigned kind,uint64_t begin,uint64_t end,uint64_t object,unsigned result) {
    if(!begin||!__atomic_load_n(&fex_short_enabled,__ATOMIC_ACQUIRE))return;
    if(end<begin||armTicksToNs(end-begin)<20000000)return;
    struct fex_short_row row={.kind=kind,.begin=begin,.end=end,.object=object,.result=result,
        .tid=fex_short_tid(),.handle=threadGetCurHandle()};
    fex_short_push(row);
}
uint64_t wine_nx_fex_short_wait_begin(unsigned tid) {
    fex_short_wait_token=0;
    uint64_t begin=wine_nx_fex_short_begin();if(!begin)return 0;
    struct fex_short_wait_slot *s=&fex_short_waits[(tid>>2)%FEX_SHORT_WAIT_SLOTS];
    if(__atomic_exchange_n(&s->busy,1,__ATOMIC_ACQUIRE)){
        __atomic_add_fetch(&fex_short_wait_lost,1,__ATOMIC_RELAXED);return begin;
    }
    if(__atomic_load_n(&s->live,__ATOMIC_ACQUIRE))__atomic_add_fetch(&fex_short_wait_lost,1,__ATOMIC_RELAXED);
    else{
        s->tid=tid;s->begin=begin;s->wakes=s->waker=s->wake_result=0;s->wake_tick=0;
        s->generation=__atomic_add_fetch(&fex_short_generation,1,__ATOMIC_RELAXED);
        fex_short_wait_token=s->generation;
        __atomic_store_n(&s->live,s->generation,__ATOMIC_RELEASE);
    }
    __atomic_store_n(&s->busy,0,__ATOMIC_RELEASE);return begin;
}
void wine_nx_fex_short_alert(unsigned target,unsigned caller,unsigned result) {
    if(!__atomic_load_n(&fex_short_enabled,__ATOMIC_ACQUIRE))return;
    struct fex_short_wait_slot *s=&fex_short_waits[(target>>2)%FEX_SHORT_WAIT_SLOTS];
    if(__atomic_exchange_n(&s->busy,1,__ATOMIC_ACQUIRE)){
        __atomic_add_fetch(&fex_short_wait_lost,1,__ATOMIC_RELAXED);return;
    }
    if(__atomic_load_n(&s->live,__ATOMIC_ACQUIRE)==s->generation&&s->generation&&s->tid==target){s->wakes++;s->waker=caller;s->wake_result=result;s->wake_tick=armGetSystemTick();}
    __atomic_store_n(&s->busy,0,__ATOMIC_RELEASE);
}
void wine_nx_fex_short_wait_end(unsigned tid,uint64_t begin,uint64_t object,unsigned result) {
    if(!begin)return;
    uint64_t end=armGetSystemTick();
    struct fex_short_row row={.kind=5,.tid=tid,.handle=threadGetCurHandle(),.begin=begin,.end=end,.object=object,.result=result};
    struct fex_short_wait_slot *s=&fex_short_waits[(tid>>2)%FEX_SHORT_WAIT_SLOTS];
    uint64_t token=fex_short_wait_token,expected=token;fex_short_wait_token=0;
    /* Retire independently of the metadata lock so contention can never strand
     * a slot. Unique tokens prevent one colliding waiter from retiring another. */
    if(token)__atomic_compare_exchange_n(&s->live,&expected,0,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE);
    if(token){
        if(__atomic_exchange_n(&s->busy,1,__ATOMIC_ACQUIRE))__atomic_add_fetch(&fex_short_wait_lost,1,__ATOMIC_RELAXED);
        else{
            if(s->generation==token&&s->tid==tid&&s->begin==begin){row.waker=s->waker;row.wakes=s->wakes;row.wake_result=s->wake_result;row.wake_tick=s->wake_tick;}
            else __atomic_add_fetch(&fex_short_wait_lost,1,__ATOMIC_RELAXED);
            __atomic_store_n(&s->busy,0,__ATOMIC_RELEASE);
        }
    }
    if(end>=begin&&armTicksToNs(end-begin)>=20000000)fex_short_push(row);
}
static void fex_short_present_map(void) {
    static __thread int sent;
    if(sent||!__atomic_load_n(&fex_short_enabled,__ATOMIC_ACQUIRE))return;
    struct fex_short_row row={.kind=6,.end=armGetSystemTick(),.tid=fex_short_tid(),.handle=threadGetCurHandle()};
    /* Repeat after a dropped enqueue would be useful, but drops are reported
     * explicitly; normal stage records also carry both IDs. */
    fex_short_push(row);sent=1;
}
static void fex_short_drain(void) {
    for(unsigned i=0;i<32;i++){
        struct fex_short_row r;
        if(pthread_mutex_trylock(&fex_short_queue.mutex))break;
        int have=fex_short_queue.count!=0;
        if(have){r=fex_short_queue.rows[fex_short_queue.head];fex_short_queue.head=(fex_short_queue.head+1)%FEX_SHORT_ROWS;fex_short_queue.count--;}
        pthread_mutex_unlock(&fex_short_queue.mutex);if(!have)break;
        log_line("[FEX3-SHORT] kind=%u tid=%u handle=%u begin_tick=%llu end_tick=%llu object=%llu result=%u waker=%u wakes=%u wake_result=%u wake_tick=%llu",
          r.kind,r.tid,r.handle,(unsigned long long)r.begin,(unsigned long long)r.end,(unsigned long long)r.object,r.result,
          r.waker,r.wakes,r.wake_result,(unsigned long long)r.wake_tick);
    }
    for(unsigned i=0;i<32;i++){
        char text[FEX_SHORT_BYTES];
        if(pthread_mutex_trylock(&fex_short_text.mutex))break;
        int have=fex_short_text.count!=0;
        if(have){memcpy(text,fex_short_text.rows[fex_short_text.head],sizeof(text));fex_short_text.head=(fex_short_text.head+1)%FEX_SHORT_TEXT;fex_short_text.count--;}
        pthread_mutex_unlock(&fex_short_text.mutex);if(!have)break;
        log_line("%s",text);
    }
}
static void fex_short_report(void) {
    if(!__atomic_load_n(&fex_short_enabled,__ATOMIC_ACQUIRE))return;
    log_line("[FEX3-SHORT-STATS] tick=%llu rows=%llu row_dropped=%llu jit_rows=%llu jit_dropped=%llu wait_pair_lost=%llu; cumulative, missing wake is not proof of lost wake",
      (unsigned long long)armGetSystemTick(),(unsigned long long)__atomic_load_n(&fex_short_queue.queued,__ATOMIC_RELAXED),
      (unsigned long long)__atomic_load_n(&fex_short_queue.dropped,__ATOMIC_RELAXED),
      (unsigned long long)__atomic_load_n(&fex_short_text.queued,__ATOMIC_RELAXED),
      (unsigned long long)__atomic_load_n(&fex_short_text.dropped,__ATOMIC_RELAXED),
      (unsigned long long)__atomic_load_n(&fex_short_wait_lost,__ATOMIC_RELAXED));
}
