/* Live-game observer: model kernel failures; use real pthread mutexes. */
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef unsigned Handle,Result;
typedef uint64_t u64;
#define R_SUCCEEDED(x) ((x)==0)
#define R_FAILED(x) ((x)!=0)
#define NX_PROF_MAX_THREADS 128
enum {InfoType_ThreadTickCount=25,InfoType_ThreadTickCountDeprecated=14,
      ThreadActivity_Runnable=0,ThreadActivity_Paused=1};
typedef union {uint64_t x;} Register;
typedef struct {Register cpu_gprs[29];uint64_t fp,lr,sp;Register pc;} ThreadContext;
static pthread_mutex_t registry_mutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t profile_mutex=PTHREAD_MUTEX_INITIALIZER;
static struct {unsigned handle,tid;char kind;} registry[NX_PROF_MAX_THREADS];
static unsigned supported=1,paused,pauses,reads,resumes,fail_pause,fail_read,fail_resume,fail_ticks;
static uint64_t clock_ticks;
static uint64_t armGetSystemTick(void){return ++clock_ticks;}
static uint64_t armTicksToNs(uint64_t n){return n*1000;}
static Handle threadGetCurHandle(void){return 99;}
static int envIsSyscallHinted(unsigned call){assert(call==0x32||call==0x33);return supported;}
static void guarded(void){
    /* A thread cannot finish unregister/close during context collection. */
    assert(pthread_mutex_trylock(&profile_mutex)==EBUSY);
    assert(!pthread_mutex_trylock(&registry_mutex));pthread_mutex_unlock(&registry_mutex);
}
static Result svcGetInfo(u64 *ticks,unsigned type,Handle handle,uint64_t id){
    guarded();assert(!paused&&handle==42&&id==UINT64_MAX);
    if(type==InfoType_ThreadTickCount&&fail_ticks)return 7;
    assert(type==InfoType_ThreadTickCount||type==InfoType_ThreadTickCountDeprecated);
    *ticks=123456;return 0;
}
static Result svcSetThreadActivity(Handle handle,unsigned activity){
    guarded();assert(handle==42);
    if(activity==ThreadActivity_Paused){
        assert(!paused);pauses++;if(fail_pause)return 1;paused=1;return 0;
    }
    assert(activity==ThreadActivity_Runnable&&paused);resumes++;
    if(fail_resume){fail_resume--;return 2;}
    paused=0;return 0;
}
static Result svcGetThreadContext3(ThreadContext *ctx,Handle handle){
    guarded();assert(paused&&handle==42);reads++;
    if(fail_read)return 3;
    memset(ctx,0,sizeof(*ctx));
    ctx->pc.x=0x12345678;ctx->lr=0xabcdef;ctx->sp=0x80000000;ctx->fp=0x80001000;
    for(unsigned i=0;i<29;i++)ctx->cpu_gprs[i].x=0x1000+i;
    return 0;
}
#include "../src/runtime/fextendo_live_threads.h"
int main(void){
    struct fx_live_snapshot snapshot;
    registry[0].handle=99;registry[0].tid=1;registry[0].kind='w';
    registry[1].handle=42;registry[1].tid=2;registry[1].kind='s';
    pthread_mutex_lock(&profile_mutex);wine_nx_live_threads_snapshot(&snapshot);
    assert(snapshot.status==1&&!snapshot.count&&!pauses);pthread_mutex_unlock(&profile_mutex);
    pthread_mutex_lock(&registry_mutex);wine_nx_live_threads_snapshot(&snapshot);
    assert(snapshot.status==2&&!snapshot.count&&!pauses);pthread_mutex_unlock(&registry_mutex);
    assert(!pthread_mutex_trylock(&profile_mutex));pthread_mutex_unlock(&profile_mutex);
    wine_nx_live_threads_snapshot(&snapshot);
    assert(!snapshot.status&&snapshot.count==1&&snapshot.context_supported&&snapshot.elapsed_us);
    struct fx_live_thread *r=&snapshot.rows[0];
    assert(r->handle==42&&r->tid==2&&r->kind=='s'&&r->ticks==123456);
    assert(r->pc==0x12345678&&r->lr==0xabcdef&&r->x0==0x1000&&r->x28==0x101c);
    assert(!r->pause_result&&!r->read_result&&!r->resume_result&&!paused&&pauses==1&&reads==1&&resumes==1);
    fail_ticks=1;supported=0;wine_nx_live_threads_snapshot(&snapshot);
    assert(!r->ticks_result&&r->ticks==123456&&!snapshot.context_supported&&pauses==1);
    supported=1;fail_pause=1;wine_nx_live_threads_snapshot(&snapshot);
    assert(r->pause_result==1&&r->read_result==~0u&&r->resume_result==~0u&&reads==1&&resumes==1);
    fail_pause=0;fail_read=1;wine_nx_live_threads_snapshot(&snapshot);
    assert(r->read_result==3&&!r->resume_result&&!paused&&resumes==2&&!r->pc);
    fail_read=0;fail_resume=1;wine_nx_live_threads_snapshot(&snapshot);
    assert(!r->resume_result&&!paused&&resumes==4&&!snapshot.disabled);
    fail_resume=2;wine_nx_live_threads_snapshot(&snapshot);
    assert(r->resume_result==2&&paused&&snapshot.disabled&&resumes==6);
    paused=0;unsigned attempts=pauses;wine_nx_live_threads_snapshot(&snapshot);
    assert(snapshot.disabled&&pauses==attempts&&!r->pc&&r->ticks==123456);
    puts("PASS: live snapshot excludes self, try-lock contention, handle lifetime guard, CPU-tick fallback, read/pause errors, immediate resume/retry and disable after resume failure");
}
