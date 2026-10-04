/* SPDX-License-Identifier: MIT
 * Last-resort FEX CPU data storage from fragmented heap pages. Scratch, lookup
 * and private CRT allocations share this path regardless of request size.
 * Only the contiguous RW alias is published; sources stay owned until every
 * alias is unmapped. No executable/GPU memory or per-access copying here. */
#ifndef PES13_HORIZON_SCRATCH_PAGES_H
#define PES13_HORIZON_SCRATCH_PAGES_H
#define FX_SP_SLOTS 128u
#define FX_SP_MIN PAGE_BYTES
#define FX_SP_CHUNK (1024u*1024u)
#define FX_SP_BUDGET (128u*1024u*1024u)
#define FX_SP_MAX FX_SP_BUDGET
#define FX_SP_PIECES (FX_SP_BUDGET/PAGE_BYTES)
#define FX_SP_NONE UINT32_MAX
enum {FX_SP_FREE,FX_SP_BUILDING,FX_SP_LIVE,FX_SP_RELEASING,FX_SP_QUARANTINE};
struct fx_sp_piece {void *source;size_t size,offset;unsigned mapped,next;};
struct fx_sp_slot {
    void *alias;size_t size;VirtmemReservation *reservation;
    void *cpu_address;
    unsigned state,count,first,last;
};
static struct fx_sp_slot fx_sp_slots[FX_SP_SLOTS];
/* Shared descriptors cover the entire byte budget even at 4-KiB granularity.
 * Metadata is bounded/static so recovery doesn't need another heap malloc.
 * A buffer consumes only as many descriptors as its actual fragments need. */
static struct fx_sp_piece fx_sp_pieces[FX_SP_PIECES];
static unsigned fx_sp_piece_head,fx_sp_piece_ready;
#ifdef __SWITCH__
static host_mutex fx_sp_lock;
#else
static host_mutex fx_sp_lock=PTHREAD_MUTEX_INITIALIZER;
#endif
/* attempts, recovered, failed, held bytes, peak bytes, held slots, pieces,
 * returned, map failures, unmap failures, quarantined, invalid release,
 * last kernel Result, last requested size, budget refusals. */
static uint64_t fx_sp_stats[15];
static size_t fx_sp_held;
/* Ordinary native-heap frees should not scan fallback ownership or take its
 * lock. Bounds only expand; successful allocation publishes them before the
 * caller can receive an alias. Interior/quarantined aliases still get checked. */
static uintptr_t fx_sp_alias_low=UINTPTR_MAX,fx_sp_alias_high;
static void fx_sp_publish_range(uintptr_t lo,uintptr_t hi){
    uintptr_t old=__atomic_load_n(&fx_sp_alias_low,__ATOMIC_RELAXED);
    while(lo<old&&!__atomic_compare_exchange_n(&fx_sp_alias_low,&old,lo,0,__ATOMIC_RELAXED,__ATOMIC_RELAXED)){}
    old=__atomic_load_n(&fx_sp_alias_high,__ATOMIC_RELAXED);
    while(hi>old&&!__atomic_compare_exchange_n(&fx_sp_alias_high,&old,hi,0,__ATOMIC_RELAXED,__ATOMIC_RELAXED)){}
}
static unsigned fx_sp_piece_take(void){
    HOST_LOCK(&fx_sp_lock);
    if(!fx_sp_piece_ready){
        for(unsigned i=0;i<FX_SP_PIECES;i++)fx_sp_pieces[i].next=i+1;
        fx_sp_pieces[FX_SP_PIECES-1].next=FX_SP_NONE;
        fx_sp_piece_ready=1;
    }
    unsigned i=fx_sp_piece_head;
    if(i!=FX_SP_NONE)fx_sp_piece_head=fx_sp_pieces[i].next;
    HOST_UNLOCK(&fx_sp_lock);
    return i;
}
static void fx_sp_add(unsigned n,uint64_t v){__atomic_fetch_add(&fx_sp_stats[n],v,__ATOMIC_RELAXED);}
static void fx_sp_peak(uint64_t n){
    uint64_t old=__atomic_load_n(&fx_sp_stats[4],__ATOMIC_RELAXED);
    while(old<n&&!__atomic_compare_exchange_n(&fx_sp_stats[4],&old,n,0,__ATOMIC_RELAXED,__ATOMIC_RELAXED)){}
}
static void fx_sp_quarantine(struct fx_sp_slot *s){
    fx_sp_add(10,1);
    fx_sp_publish_range((uintptr_t)s->alias,(uintptr_t)s->alias+s->size);
    HOST_LOCK(&fx_sp_lock);s->state=FX_SP_QUARANTINE;HOST_UNLOCK(&fx_sp_lock);
}
/* Preserve the reservation and every source allocation if even one unmap
 * fails. A caller can never receive a partially mapped or recycled buffer. */
static int fx_sp_dispose(struct fx_sp_slot *s){
    int failed=0;
    for(unsigned i=s->first;i!=FX_SP_NONE;i=fx_sp_pieces[i].next){
        struct fx_sp_piece *p=&fx_sp_pieces[i];
        if(!p->mapped)continue;
        Result rc=svcUnmapMemory((char *)s->alias+p->offset,p->source,p->size);
        if(R_FAILED(rc)){
            __atomic_store_n(&fx_sp_stats[12],rc,__ATOMIC_RELAXED);fx_sp_add(9,1);failed=1;
        }else p->mapped=0;
    }
    if(failed){fx_sp_quarantine(s);return 0;}
    if(s->reservation){virtmemLock();virtmemRemoveReservation(s->reservation);virtmemUnlock();}
    for(unsigned i=s->first;i!=FX_SP_NONE;i=fx_sp_pieces[i].next)free(fx_sp_pieces[i].source);
    fx_sp_add(6,-(uint64_t)s->count);
    HOST_LOCK(&fx_sp_lock);
    if(s->count){fx_sp_pieces[s->last].next=fx_sp_piece_head;fx_sp_piece_head=s->first;}
    fx_sp_held-=s->size;fx_sp_add(3,-(uint64_t)s->size);fx_sp_add(5,-UINT64_C(1));
    s->alias=NULL;s->reservation=NULL;s->cpu_address=NULL;s->count=0;s->size=0;s->state=FX_SP_FREE;
    HOST_UNLOCK(&fx_sp_lock);
    return 1;
}
static __attribute__((noinline,used)) void *fx_scratch_pages_take(size_t size){
    if(!size||size>FX_SP_MAX||size%PAGE_BYTES)return NULL;
    fx_sp_add(0,1);__atomic_store_n(&fx_sp_stats[13],size,__ATOMIC_RELAXED);
    struct fx_sp_slot *s=NULL;
    HOST_LOCK(&fx_sp_lock);
    if(size<=FX_SP_BUDGET-fx_sp_held){
        for(unsigned i=0;i<FX_SP_SLOTS;i++)if(fx_sp_slots[i].state==FX_SP_FREE){
            s=&fx_sp_slots[i];s->state=FX_SP_BUILDING;s->size=size;
            s->alias=NULL;s->reservation=NULL;s->cpu_address=NULL;s->count=0;
            s->first=s->last=FX_SP_NONE;
            fx_sp_held+=size;fx_sp_add(3,size);fx_sp_add(5,1);fx_sp_peak(fx_sp_held);break;
        }
    }
    HOST_UNLOCK(&fx_sp_lock);
    if(!s){fx_sp_add(14,1);fx_sp_add(2,1);return NULL;}
    size_t left=size,ceiling=FX_SP_CHUNK;
    while(left){
        size_t n=left<ceiling?left:ceiling;
        void *p;
        while(!(p=aligned_alloc(PAGE_BYTES,n))){
            if(n<=FX_SP_MIN)break;
            n=(n/2)&~(size_t)(PAGE_BYTES-1);
            if(n<FX_SP_MIN)n=FX_SP_MIN;
            ceiling=n;
        }
        if(!p)goto failed;
        unsigned i=fx_sp_piece_take();
        if(i==FX_SP_NONE){free(p);goto failed;}
        fx_sp_pieces[i]=(struct fx_sp_piece){p,n,size-left,0,FX_SP_NONE};
        if(s->count)fx_sp_pieces[s->last].next=i;
        else s->first=i;
        s->last=i;s->count++;
        fx_sp_add(6,1);left-=n;
    }
    if(left)goto failed;
    virtmemLock();
    s->alias=virtmemFindStack(size,PAGE_BYTES);
    if(s->alias)s->reservation=virtmemAddReservation(s->alias,size);
    virtmemUnlock();
    if(!s->alias||!s->reservation)goto failed;
    for(unsigned i=s->first;i!=FX_SP_NONE;i=fx_sp_pieces[i].next){
        struct fx_sp_piece *p=&fx_sp_pieces[i];
        Result rc=svcMapMemory((char *)s->alias+p->offset,p->source,p->size);
        if(R_FAILED(rc)){
            fx_sp_add(8,1);__atomic_store_n(&fx_sp_stats[12],rc,__ATOMIC_RELAXED);goto failed;
        }
        p->mapped=1;
    }
    fx_sp_publish_range((uintptr_t)s->alias,(uintptr_t)s->alias+s->size);
    HOST_LOCK(&fx_sp_lock);s->state=FX_SP_LIVE;HOST_UNLOCK(&fx_sp_lock);
    fx_sp_add(1,1);return s->alias;
failed:
    fx_sp_add(2,1);fx_sp_dispose(s);return NULL;
}
/* Return 1 for owned/interior/quarantined aliases so libc never sees them. */
static __attribute__((noinline,used)) int fx_scratch_pages_release(void *address){
    struct fx_sp_slot *s=NULL;uintptr_t at=(uintptr_t)address;
    if(at<__atomic_load_n(&fx_sp_alias_low,__ATOMIC_RELAXED)||
       at>=__atomic_load_n(&fx_sp_alias_high,__ATOMIC_RELAXED))return 0;
    HOST_LOCK(&fx_sp_lock);
    for(unsigned i=0;i<FX_SP_SLOTS;i++){
        struct fx_sp_slot *p=&fx_sp_slots[i];
        if(p->state==FX_SP_FREE||p->state==FX_SP_BUILDING||!p->alias||
           at<(uintptr_t)p->alias||at-(uintptr_t)p->alias>=p->size)continue;
        if(at!=(uintptr_t)p->alias||p->state!=FX_SP_LIVE){
            fx_sp_add(11,1);HOST_UNLOCK(&fx_sp_lock);return 1;
        }
        s=p;s->state=FX_SP_RELEASING;break;
    }
    HOST_UNLOCK(&fx_sp_lock);
    if(!s)return 0;
    if(fx_sp_dispose(s))fx_sp_add(7,1);
    return 1;
}
void pes13_fex_scratch_pages_snapshot(uint64_t out[15]){
    for(unsigned i=0;i<15;i++)out[i]=__atomic_load_n(&fx_sp_stats[i],__ATOMIC_RELAXED);
}
/* Native Rust's shader compiler owns ordinary CPU data, not driver/GPU
 * allocations. It can use the same bounded pages only after its normal
 * allocator fails. Keep ownership in static metadata, never before a foreign
 * pointer: native malloc pointers have no custom header. */
void *pes13_cpu_pages_allocate(size_t size,size_t alignment){
    if(!size||!alignment||(alignment&(alignment-1))||alignment>FX_SP_BUDGET)return NULL;
    size_t padding=alignment>PAGE_BYTES?alignment-1:0;
    if(size>SIZE_MAX-padding-(PAGE_BYTES-1))return NULL;
    size_t rounded=(size+padding+PAGE_BYTES-1)&~(size_t)(PAGE_BYTES-1);
    void *raw=fx_scratch_pages_take(rounded);
    if(!raw)return NULL;
    void *user=(void *)(((uintptr_t)raw+alignment-1)&~(uintptr_t)(alignment-1));
    HOST_LOCK(&fx_sp_lock);
    for(unsigned i=0;i<FX_SP_SLOTS;i++)if(fx_sp_slots[i].alias==raw&&fx_sp_slots[i].state==FX_SP_LIVE){
        fx_sp_slots[i].cpu_address=user;break;
    }
    HOST_UNLOCK(&fx_sp_lock);
    return user;
}
/* Shared read/release lookup. An ordinary pointer outside the alias range
 * takes no lock; the native fast path retains its original allocator. */
static void *fx_cpu_pages_owner(void *address){
    uintptr_t at=(uintptr_t)address;void *raw=NULL;
    if(at<__atomic_load_n(&fx_sp_alias_low,__ATOMIC_RELAXED)||
       at>=__atomic_load_n(&fx_sp_alias_high,__ATOMIC_RELAXED))return NULL;
    HOST_LOCK(&fx_sp_lock);
    for(unsigned i=0;i<FX_SP_SLOTS;i++){
        struct fx_sp_slot *s=&fx_sp_slots[i];
        if(s->cpu_address==address&&s->state!=FX_SP_FREE){raw=s->alias;break;}
    }
    HOST_UNLOCK(&fx_sp_lock);
    return raw;
}
int pes13_cpu_pages_owned(void *address){return fx_cpu_pages_owner(address)!=NULL;}
int pes13_cpu_pages_release(void *address){
    void *raw=fx_cpu_pages_owner(address);
    return raw?fx_scratch_pages_release(raw):0;
}
#endif
