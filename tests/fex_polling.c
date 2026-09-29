/* Harness around actual generated Wine functions and the production headers.
 * Kernel sleep/time are controlled seams; no host timing/FPS assertion. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#define __SWITCH__ 1
#define WINAPI
#define STATUS_SUCCESS 0
#define STATUS_INVALID_SYSTEM_SERVICE ((int)0xc000001c)
#define FALSE 0
typedef int NTSTATUS, BOOL;
typedef unsigned char BOOLEAN;
typedef uintptr_t ULONG_PTR;
typedef uint64_t ULONGLONG;
typedef union {int64_t QuadPart;} LARGE_INTEGER;
typedef struct {struct {uintptr_t UniqueThread;} ClientId;} TEB;
typedef struct {void **ServiceTable;void *CounterTable;uintptr_t ServiceLimit;unsigned char *ArgumentTable;} SYSTEM_SERVICE_TABLE;
static __thread TEB teb;
static __thread uint64_t now=1000000, yield_cost, extra_pause, reads, yields, pauses, notes, note_us;
static unsigned shared_rmw, traces, delay_impl_calls, completed;
static int wine_nx_runtime_verbose, wine_nx_fex_yield_backoff=1;
static unsigned wine_nx_syscalls,wine_nx_syscall_counts[0x2000];
static SYSTEM_SERVICE_TABLE KeServiceDescriptorTable[4];
static TEB *NtCurrentTeb(void){return &teb;}
#define HandleToULong(h) ((unsigned)(h))
static ULONGLONG monotonic_counter(void){++reads;return now;}
static void svcSleepThread(int64_t ns){if(!ns){++yields;now+=yield_cost;}else{assert(ns==50000);++pauses;now+=500+extra_pause;}}
static uint64_t wine_nx_fex_frame_tick(void){return monotonic_counter();}
static void wine_nx_fex_yield_pause_note(unsigned tid,uint64_t us){assert(tid);assert(us>=50);}
static void wine_nx_fex_delay_zero_note(unsigned tid,uint64_t us){assert(tid);++notes;note_us+=us;}
static void wine_nx_fex_delay_note(unsigned tid,int alertable,int has,int64_t timeout,uint64_t begin,int status){
    (void)alertable;(void)has;(void)timeout;(void)status;
    wine_nx_fex_delay_zero_note(tid,(monotonic_counter()-begin)/10);
}
static void wine_nx_runtime_trace(const char *line){assert(line[0]);__atomic_add_fetch(&traces,1,__ATOMIC_RELAXED);}
static NTSTATUS NtYieldExecution(void);
static NTSTATUS fex_delay_impl(BOOLEAN alertable,const LARGE_INTEGER *timeout){
    __atomic_add_fetch(&delay_impl_calls,1,__ATOMIC_RELAXED);
    if(alertable)return 0xc0;
    if(timeout&&!timeout->QuadPart)return NtYieldExecution();
    return 0x17;
}
static NTSTATUS NtReadVirtualMemory(void){return 0x27;}
static NTSTATUS wide_call(ULONG_PTR a0,ULONG_PTR a1,ULONG_PTR a2,ULONG_PTR a3,
                         ULONG_PTR a4,ULONG_PTR a5,ULONG_PTR a6,ULONG_PTR a7,
                         ULONG_PTR a8,ULONG_PTR a9,ULONG_PTR a10,ULONG_PTR a11,
                         ULONG_PTR a12,ULONG_PTR a13,ULONG_PTR a14,ULONG_PTR a15){
    return a0+a1+a2+a3+a4+a5+a6+a7+a8+a9+a10+a11+a12+a13+a14+a15;
}
static unsigned counted_add(unsigned *p,unsigned value,int order){
    __atomic_add_fetch(&shared_rmw,1,__ATOMIC_RELAXED);
    return __atomic_add_fetch(p,value,order);
}
/* PRODUCTION_FUNCTIONS */

static NTSTATUS invoke(unsigned id,ULONG_PTR a,ULONG_PTR b){return wine_nx_do_syscall(NULL,a,b,0,0,0,0,0,0,id);}
static void *worker(void *arg){
    teb.ClientId.UniqueThread=(uintptr_t)arg;
    LARGE_INTEGER counter,freq,zero={0};
    for(unsigned i=0;i<5000;i++){
        assert(!invoke(0x31,(uintptr_t)&counter,(uintptr_t)&freq));assert(counter.QuadPart==(int64_t)now&&freq.QuadPart==10000000);
        assert(!invoke(0x34,0,(uintptr_t)&zero));
    }
    __atomic_add_fetch(&completed,1,__ATOMIC_RELEASE);return NULL;
}
static void reset(void){
    memset(fex_poll_slots,0,sizeof(fex_poll_slots));memset(&fex_poll_local,0,sizeof(fex_poll_local));
    memset(wine_nx_syscall_counts,0,sizeof(wine_nx_syscall_counts));fex_poll_claimed=0;
    wine_nx_syscalls=shared_rmw=delay_impl_calls=traces=0;
}
int main(void){
    _Static_assert(sizeof(struct fex_poll_slot)==64,"isolated cache lines");
    static void *handlers[64];static unsigned char sizes[64];
    handlers[0x31]=(void*)NtQueryPerformanceCounter;handlers[0x34]=(void*)NtDelayExecution;
    handlers[7]=(void*)NtReadVirtualMemory;handlers[9]=(void*)wide_call;sizes[9]=128;
    KeServiceDescriptorTable[0]=(SYSTEM_SERVICE_TABLE){handlers,NULL,64,sizes};
    KeServiceDescriptorTable[1]=KeServiceDescriptorTable[0];teb.ClientId.UniqueThread=4;
    unsigned totals[2];LARGE_INTEGER counter,freq,zero={0},negative={-10000};
    assert(invoke(0x2001,0,0)==STATUS_INVALID_SYSTEM_SERVICE);
    assert(invoke(0x40,0,0)==STATUS_INVALID_SYSTEM_SERVICE);assert(invoke(3,0,0)==STATUS_INVALID_SYSTEM_SERVICE);
    assert(!wine_nx_syscalls);
    /* Ordinary service routing, optional frequency, NULL stack and wide args. */
    assert(!invoke(0x31,(uintptr_t)&counter,0));assert(counter.QuadPart==(int64_t)now);
    assert(invoke(7,0,0)==0x27);assert(!wine_nx_syscalls);
    ULONG_PTR stack[]={9,10,11,12,13,14,15,16};
    assert(wine_nx_do_syscall(stack,1,2,3,4,5,6,7,8,9)==136);
    assert(wine_nx_do_syscall(NULL,1,2,3,4,5,6,7,8,9)==36);
    assert(!invoke(0x1031,(uintptr_t)&counter,(uintptr_t)&freq));assert(wine_nx_syscall_counts[0x1031]==1);
    wine_nx_runtime_verbose=1;assert(!invoke(0x31,(uintptr_t)&counter,(uintptr_t)&freq));assert(traces==2);wine_nx_runtime_verbose=0;
    assert(invoke(0x34,1,(uintptr_t)&zero)==0xc0);
    assert(invoke(0x34,0,(uintptr_t)&negative)==0x17);
    assert(invoke(0x34,0,0)==0x17);
    /* The OFF path publishes every event into the original global counters. */
    reset();wine_nx_fex_polling=0;
    for(unsigned i=0;i<128;i++){assert(!invoke(0x31,(uintptr_t)&counter,0));assert(!invoke(0x34,0,(uintptr_t)&zero));}
    assert(shared_rmw==512&&wine_nx_syscalls==256);
    wine_nx_fex_poll_totals(totals);assert(!totals[0]&&!totals[1]);
    /* Many producers, live snapshots, then exact totals even after exit. */
    reset();wine_nx_fex_polling=1;pthread_t threads[8];completed=0;
    for(unsigned i=0;i<8;i++)assert(!pthread_create(&threads[i],NULL,worker,(void*)(uintptr_t)(4*(i+1))));
    unsigned prev[2]={0};
    while(__atomic_load_n(&completed,__ATOMIC_ACQUIRE)!=8){wine_nx_fex_poll_totals(totals);for(unsigned i=0;i<2;i++){assert(totals[i]>=prev[i]&&totals[i]<=40000);prev[i]=totals[i];}}
    for(unsigned i=0;i<8;i++)assert(!pthread_join(threads[i],NULL));
    wine_nx_fex_poll_totals(totals);assert(totals[0]==40000&&totals[1]==40000);
    assert(!shared_rmw&&!wine_nx_syscalls&&!delay_impl_calls);
    /* Counter wrap, nested observation, saturation and tail preservation. */
    reset();assert(fex_poll_count(0x31));fex_poll_local.value[0]=UINT32_MAX;
    assert(fex_poll_count(0x31));wine_nx_fex_poll_totals(totals);assert(!totals[0]);
    fex_poll_local.busy=1;assert(!fex_poll_count(0x31));fex_poll_local.busy=0;
    reset();for(unsigned i=0;i<FEX_POLL_SLOTS;i++){memset(&fex_poll_local,0,sizeof(fex_poll_local));assert(fex_poll_count(0x31));}
    memset(&fex_poll_local,0,sizeof(fex_poll_local));assert(!invoke(0x31,(uintptr_t)&counter,0));
    wine_nx_fex_poll_totals(totals);assert(totals[0]==256&&wine_nx_syscall_counts[0x31]==1&&shared_rmw==2&&fex_poll_claimed==256);
    /* Sparse calls isolate diagnostics overhead from the backoff threshold. */
    wine_nx_fex_yield_backoff=0;reads=yields=notes=0;
    for(unsigned i=0;i<1000;i++)assert(!NtDelayExecution(0,&zero));
    assert(reads==2000&&yields==1000&&notes==1000);
    wine_nx_fex_polling=0;wine_nx_fex_yield_backoff=1;reads=yields=notes=0;
    for(unsigned i=0;i<1000;i++){now+=30000;assert(!NtDelayExecution(0,&zero));}
    assert(reads==4000&&yields==1000&&notes==1000);
    wine_nx_fex_polling=1;reads=yields=notes=0;
    for(unsigned i=0;i<1000;i++){now+=30000;assert(!NtDelayExecution(0,&zero));}
    assert(reads==2000&&yields==1000&&notes==1000);
    /* Both optimized APIs share the same burst, including the 64th call. */
    now+=30000;pauses=0;
    for(unsigned i=0;i<64;i++){now+=100;if(i&1)assert(!NtYieldExecution());else assert(!NtDelayExecution(0,&zero));}
    assert(pauses==1);
    yield_cost=20;pauses=0;for(unsigned i=0;i<128;i++)assert(!NtDelayExecution(0,&zero));assert(!pauses);
    puts("PASS exact generated dispatch: 8 producers, 80000 hot calls, 0 shared RMW after slot claims; OFF/overflow fallback, live/exit totals, wrap, handler/ID/argument routing, APC/nonzero delegation; zero-delay clock reads 4 -> 2 and shared backoff thresholds.");
}
