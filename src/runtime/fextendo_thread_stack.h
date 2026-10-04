/* LGPL-2.1-or-later. Emergency stacks for native libnx threads. Keep libnx's
 * original stack/TLS layout and map/create/close lifecycle. No guest ABI change. */
#ifndef FX_THREAD_STACK_HEADER
#define FX_THREAD_STACK_HEADER
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#ifndef FX_STACK_HOST_TEST
#include <sys/reent.h>
extern unsigned char __tls_start[], __tls_end[];
#endif

#define FX_STACK_SLOTS 8
#define FX_STACK_LIMIT (1024u * 1024u)
#define FX_STACK_PAGE 4096u
enum { FX_STACK_FREE, FX_STACK_USED, FX_STACK_RELEASING, FX_STACK_QUARANTINED };
struct fx_stack_slot { void *base; unsigned state; };
static struct fx_stack_slot fx_stack_slots[FX_STACK_SLOTS];
static size_t fx_stack_bytes;
static unsigned fx_stack_ready;
/* capacity, bytes per slot, used (including quarantined), peak, recovered,
 * returned, exhausted, quarantined, invalid release, create calls/failures,
 * last failing Result/stack size, init failures, allocation failures. */
static uint64_t fx_stack_stats[15];
static __thread size_t fx_stack_request;

extern void *__real___libnx_aligned_alloc(size_t,size_t);
extern void __real___libnx_free(void *);
extern Result __real_threadCreate(Thread *,void (*)(void *),void *,void *,size_t,int,int);

static void fx_stack_count(unsigned n) {
    __atomic_add_fetch(&fx_stack_stats[n],1,__ATOMIC_RELAXED);
}
static __attribute__((noinline,used)) void fx_thread_stack_init(void) {
    unsigned expected=0;
    if(!__atomic_compare_exchange_n(&fx_stack_ready,&expected,1,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return;
    int saved=errno;
#ifdef FX_STACK_HOST_TEST
    size_t overhead=FX_STACK_TEST_OVERHEAD;
#else
    size_t overhead=(((uintptr_t)__tls_end-(uintptr_t)__tls_start+15)&~(size_t)15)+
                    ((sizeof(struct _reent)+15)&~(size_t)15);
#endif
    /* Reject impossible linker/layout metadata instead of underallocating. */
    if(overhead>64*1024) { fx_stack_count(13); goto ready; }
    fx_stack_bytes=(FX_STACK_LIMIT+overhead+FX_STACK_PAGE-1)&~(size_t)(FX_STACK_PAGE-1);
    fx_stack_stats[1]=fx_stack_bytes;
    for(unsigned i=0;i<FX_STACK_SLOTS;i++) {
        void *p=__real___libnx_aligned_alloc(FX_STACK_PAGE,fx_stack_bytes);
        if(!p) { fx_stack_count(13); break; }
        fx_stack_slots[i].base=p;
        fx_stack_count(0);
    }
ready:
    __atomic_store_n(&fx_stack_ready,2,__ATOMIC_RELEASE);
    errno=saved;
}

void *__wrap___libnx_aligned_alloc(size_t alignment,size_t size) {
    int saved=errno;
    void *p=__real___libnx_aligned_alloc(alignment,size);
    if(p||!fx_stack_request||fx_stack_request>FX_STACK_LIMIT||
       alignment!=FX_STACK_PAGE||!size||
       __atomic_load_n(&fx_stack_ready,__ATOMIC_ACQUIRE)!=2||size>fx_stack_bytes)return p;
    fx_stack_count(14);
    for(unsigned i=0;i<FX_STACK_SLOTS;i++) {
        unsigned expected=FX_STACK_FREE;
        if(!fx_stack_slots[i].base||!__atomic_compare_exchange_n(&fx_stack_slots[i].state,&expected,
            FX_STACK_USED,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))continue;
        uint64_t used=__atomic_add_fetch(&fx_stack_stats[2],1,__ATOMIC_RELAXED);
        uint64_t peak=__atomic_load_n(&fx_stack_stats[3],__ATOMIC_RELAXED);
        while(used>peak&&!__atomic_compare_exchange_n(&fx_stack_stats[3],&peak,used,0,__ATOMIC_RELAXED,__ATOMIC_RELAXED)){}
        fx_stack_count(4);errno=saved;return fx_stack_slots[i].base;
    }
    fx_stack_count(6);return NULL;
}

/* libnx frees a stack only after unmapping its alias. Verify the entire
 * allocation: its create-failure rollback does not check svcUnmapMemory. */
static int fx_stack_reusable(void *pointer) {
    uintptr_t at=(uintptr_t)pointer,end=at+fx_stack_bytes;
    while(at<end) {
        MemoryInfo info;u32 page;
        if(R_FAILED(svcQueryMemory(&info,&page,at))||info.addr>at||!info.size||
           info.addr>UINTPTR_MAX-info.size||info.addr+info.size<=at||
           info.type!=MemType_Heap||info.perm!=Perm_Rw||
           (info.attr&(MemAttr_IsBorrowed|MemAttr_IsIpcMapped|MemAttr_IsDeviceMapped)))return 0;
        at=info.addr+info.size;
    }
    return 1;
}

void __wrap___libnx_free(void *pointer) {
    if(pointer&&__atomic_load_n(&fx_stack_ready,__ATOMIC_ACQUIRE)==2) {
        uintptr_t at=(uintptr_t)pointer;
        for(unsigned i=0;i<FX_STACK_SLOTS;i++) {
            uintptr_t base=(uintptr_t)fx_stack_slots[i].base;
            if(!base||at<base||at-base>=fx_stack_bytes)continue;
            unsigned expected=FX_STACK_USED;
            if(at!=base||!__atomic_compare_exchange_n(&fx_stack_slots[i].state,&expected,
                FX_STACK_RELEASING,0,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE)) { fx_stack_count(8); return; }
            if(!fx_stack_reusable(pointer)) {
                fx_stack_count(7);
                __atomic_store_n(&fx_stack_slots[i].state,FX_STACK_QUARANTINED,__ATOMIC_RELEASE);
                return;
            }
            __atomic_sub_fetch(&fx_stack_stats[2],1,__ATOMIC_RELAXED);fx_stack_count(5);
            __atomic_store_n(&fx_stack_slots[i].state,FX_STACK_FREE,__ATOMIC_RELEASE);
            return;
        }
    }
    __real___libnx_free(pointer);
}

Result __wrap_threadCreate(Thread *t,void (*entry)(void *),void *arg,void *stack,
                          size_t size,int priority,int cpu) {
    size_t saved=fx_stack_request;
    fx_stack_request=stack?0:size;
    Result result=__real_threadCreate(t,entry,arg,stack,size,priority,cpu);
    fx_stack_request=saved;
    fx_stack_count(9);
    if(R_FAILED(result)) {
        fx_stack_count(10);
        __atomic_store_n(&fx_stack_stats[11],result,__ATOMIC_RELAXED);
        __atomic_store_n(&fx_stack_stats[12],size,__ATOMIC_RELAXED);
        wine_nx_transition_event(12,result,size,(uintptr_t)__builtin_return_address(0));
    }
    return result;
}
static void fx_thread_stack_snapshot(uint64_t out[15]) {
    for(unsigned i=0;i<15;i++)out[i]=__atomic_load_n(&fx_stack_stats[i],__ATOMIC_RELAXED);
}
#endif
