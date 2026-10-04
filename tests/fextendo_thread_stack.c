/* Native stack fallback ownership and contention under ASan/UBSan. */
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t Result;
typedef uint32_t u32;
typedef struct {void *stack;} Thread;
typedef struct {uint64_t addr,size;u32 type,attr,perm;} MemoryInfo;
enum {MemType_Heap=5,Perm_Rw=3,MemAttr_IsBorrowed=1,MemAttr_IsIpcMapped=2,MemAttr_IsDeviceMapped=4};
#define R_FAILED(x) ((x)!=0)
#define FX_STACK_HOST_TEST 1
#define FX_STACK_TEST_OVERHEAD 3280
static Result svcQueryMemory(MemoryInfo *,u32 *,uint64_t);
static void wine_nx_transition_event(unsigned,unsigned,uint64_t,uint64_t);
#include "../src/runtime/fextendo_thread_stack.h"

static int available=8,initializing=1,denied,real_frees,event_count;
static int create_error,unmap_error,query_error,second_borrowed,nest_once;
static void *bad;
static void entry(void *arg){(void)arg;}
void *__real___libnx_aligned_alloc(size_t a,size_t n) {
    if(denied||(initializing&&available--<=0)){errno=ENOMEM;return NULL;}
    void *p=NULL;assert(!posix_memalign(&p,a,(n+a-1)&~(a-1)));return p;
}
void __real___libnx_free(void *p){if(p)__atomic_add_fetch(&real_frees,1,__ATOMIC_RELAXED);free(p);}
static void wine_nx_transition_event(unsigned kind,unsigned code,uint64_t size,uint64_t caller){
    assert(kind==12&&code&&size&&caller);__atomic_add_fetch(&event_count,1,__ATOMIC_RELAXED);
}
static Result svcQueryMemory(MemoryInfo *i,u32 *page,uint64_t at){
    (void)page;
    if(query_error)return 1;
    *i=(MemoryInfo){.addr=at,.size=4096,.type=MemType_Heap,.perm=Perm_Rw};
    if(at==(uintptr_t)bad+4096&&second_borrowed)i->attr=MemAttr_IsBorrowed;
    return 0;
}
Result __real_threadCreate(Thread *t,void (*fn)(void *),void *arg,void *stack,size_t n,int priority,int cpu){
    assert(fn==entry&&arg==(void *)42&&priority==59&&cpu==-2);
    if(stack){t->stack=stack;return 0;}
    if(nest_once){
        nest_once=0;Thread child;char external[32];
        assert(fx_stack_request==n);
        assert(!__wrap_threadCreate(&child,entry,arg,external,sizeof(external),priority,cpu));
        assert(fx_stack_request==n);
    }
    void *p=__wrap___libnx_aligned_alloc(4096,(n+FX_STACK_TEST_OVERHEAD+4095)&~4095UL);
    if(!p)return 0x559;
    t->stack=p;
    if(create_error){if(unmap_error){bad=p;second_borrowed=1;}__wrap___libnx_free(p);return 0x1234;}
    return 0;
}
static Result create(Thread *t,size_t n){return __wrap_threadCreate(t,entry,(void *)42,NULL,n,59,-2);}
static pthread_barrier_t barrier;
static unsigned concurrent_success;
static void *concurrent(void *p){
    (void)p;Thread t;
    assert(!fx_stack_request);
    Result r=create(&t,FX_STACK_LIMIT);
    assert(!fx_stack_request);
    if(!r)__atomic_add_fetch(&concurrent_success,1,__ATOMIC_RELAXED);
    pthread_barrier_wait(&barrier);
    if(!r)__wrap___libnx_free(t.stack);
    return NULL;
}
int main(int argc,char **argv){
    unsigned capacity=argc>1?strtoul(argv[1],NULL,10):8;available=capacity;
    errno=EDOM;fx_thread_stack_init();assert(errno==EDOM);initializing=0;
    assert(fx_stack_stats[0]==capacity&&fx_stack_bytes==1052672);
    fx_thread_stack_init();assert(fx_stack_stats[0]==capacity);
    Thread t[9];denied=1;
    /* An unrelated libnx allocation cannot consume emergency stacks. */
    assert(!__wrap___libnx_aligned_alloc(4096,1052672));assert(!fx_stack_stats[4]);
    for(unsigned i=0;i<capacity;i++){errno=EDOM;assert(!create(&t[i],FX_STACK_LIMIT));assert(errno==EDOM);}
    assert(create(&t[capacity],FX_STACK_LIMIT)==0x559);
    assert(create(&t[capacity],2*FX_STACK_LIMIT)==0x559);
    for(unsigned i=0;i<capacity;i++)__wrap___libnx_free(t[i].stack);
    assert(!fx_stack_stats[2]);
    if(capacity){
        nest_once=1;assert(!create(t,FX_STACK_LIMIT));assert(!fx_stack_request);void *first=t[0].stack;
        __wrap___libnx_free((char *)first+4096);assert(fx_stack_stats[8]==1&&fx_stack_stats[2]==1);
        __wrap___libnx_free(first);__wrap___libnx_free(first);assert(fx_stack_stats[8]==2);
        assert(!create(t,65536));assert(t[0].stack==first);__wrap___libnx_free(first);
        create_error=1;assert(create(t,FX_STACK_LIMIT)==0x1234);assert(!fx_stack_stats[2]);
        create_error=0;
    }
    /* No pool pointer can be leased to two simultaneous native threads. */
    pthread_t ids[24];pthread_barrier_init(&barrier,NULL,24);
    for(unsigned i=0;i<24;i++)assert(!pthread_create(&ids[i],NULL,concurrent,NULL));
    for(unsigned i=0;i<24;i++)assert(!pthread_join(ids[i],NULL));
    pthread_barrier_destroy(&barrier);
    assert(concurrent_success==capacity&&!fx_stack_stats[2]);
    if(capacity){
        create_error=unmap_error=1;assert(create(t,FX_STACK_LIMIT)==0x1234);
        assert(fx_stack_stats[7]==1&&fx_stack_slots[0].state==FX_STACK_QUARANTINED);
        create_error=unmap_error=second_borrowed=0;
        if(capacity>1){assert(!create(t,FX_STACK_LIMIT));query_error=1;__wrap___libnx_free(t[0].stack);query_error=0;assert(fx_stack_stats[7]==2);}
    }
    denied=0;assert(!create(t,FX_STACK_LIMIT));__wrap___libnx_free(t[0].stack);assert(real_frees==1);
    char external[32];assert(!__wrap_threadCreate(t,entry,(void *)42,external,sizeof(external),59,-2));assert(t[0].stack==external);
    uint64_t stats[15];fx_thread_stack_snapshot(stats);assert(stats[10]==(unsigned)event_count&&stats[3]==capacity);
    for(unsigned i=0;i<capacity;i++)free(fx_stack_slots[i].base);
    printf("PASS capacity=%u: normal/fallback/exhausted, caller ownership, concurrent leases, failed create cleanup, full-range unmap quarantine\n",capacity);
}
