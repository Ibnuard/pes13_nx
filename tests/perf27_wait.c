#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include <time.h>
#include <errno.h>
#include "../src/runtime/pes13_perf27_wait.h"

static int objects[128];
static const void *handles[128];
static const void *resolve(unsigned int h,const void *self)
{ return h==0xfffffffeu ? self : (h<128 ? handles[h] : NULL); }
static void count_wake(void *v) { ++*(unsigned *)v; }
static void signal_wake(void *v) { assert(!pthread_cond_signal(v)); }
static void init_handles(void) { for(unsigned i=0;i<128;++i)handles[i]=&objects[i]; }
static void decoding(void)
{
    struct pes27_interest in;
    unsigned int data[130]={0};
    const unsigned int prefixes[]={0,10,32};
    for(unsigned pi=0;pi<3;++pi) {
        unsigned int prefix=prefixes[pi], apc_bytes=prefix ? prefix*4 : 40;
        for(unsigned count=1;count<=64;++count) {
            for(int op=1;op<=2;++op) {
                data[prefix]=op;
                for(unsigned i=0;i<count;++i)data[prefix+1+i]=i+1;
                unsigned size=4+4*count;
                pes27_decode(&in,data,size+4*prefix,size,apc_bytes,1,2,3,&objects[0]);
                assert(!in.broad && in.count==count);
                for(unsigned i=0;i<count;++i) assert(in.handles[i]==i+1);
            }
        }
        data[prefix]=3;data[prefix+1]=7;data[prefix+2]=8;
        pes27_decode(&in,data,12+4*prefix,12,apc_bytes,1,2,3,&objects[0]);
        assert(!in.broad && in.count==1 && in.handles[0]==7);
        assert(!pes27_interested(&in,&objects[8],resolve));
    }
    for(unsigned size=0;size<4;++size) {
        pes27_decode(&in,data,sizeof(data),size,128,1,2,3,NULL);assert(in.broad);
    }
    data[0]=1;
    pes27_decode(&in,data,268,268,128,1,2,3,NULL);assert(in.broad); /* too many */
    pes27_decode(&in,data,3,8,128,1,2,3,NULL);assert(in.broad); /* truncated */
    pes27_decode(&in,data,9,9,128,1,2,3,NULL);assert(in.broad); /* unaligned */
    data[0]=99;pes27_decode(&in,data,8,8,128,1,2,3,NULL);assert(in.broad);
    pes27_decode(&in,NULL,8,8,128,1,2,3,NULL);assert(in.broad);
}
static void routing(void)
{
    struct pes27_router r={0};
    struct pes27_interest in[20]={0};struct pes27_waiter ws[20]={0};unsigned count[20]={0};
    for(unsigned i=0;i<20;++i) {
        in[i].count=1;in[i].handles[0]=i+1;
        ws[i].interest=&in[i];ws[i].condition=&count[i];pes27_register(&r,&ws[i]);
    }
    for(unsigned i=0;i<100000;++i)pes27_notify(&r,&objects[1],1,resolve,count_wake);
    assert(count[0]==100000 && r.filtered==1900000 && r.notified==100000);
    for(unsigned i=1;i<20;++i)assert(!count[i]);
    handles[2]=handles[1]; /* different handles of the same object */
    pes27_notify(&r,&objects[1],1,resolve,count_wake);assert(count[1]==1);
    handles[3]=NULL; /* closed handle must return to select_status */
    pes27_notify(&r,&objects[1],1,resolve,count_wake);assert(count[2]==1);
    in[3].handles[0]=0xfffffffeu;in[3].thread=&objects[1];
    pes27_notify(&r,&objects[1],1,resolve,count_wake);assert(count[3]==1);
    /* WAIT_ALL wakes if any dependency changes; object consumption is not here. */
    in[4].count=2;in[4].handles[1]=1;
    pes27_notify(&r,&objects[1],1,resolve,count_wake);assert(count[4]==1);
    in[5].broad=1;pes27_notify(&r,&objects[1],1,resolve,count_wake);assert(count[5]==1);
    ws[6].interest=NULL;pes27_notify(&r,&objects[1],1,resolve,count_wake);assert(count[6]==1);
    pes27_notify(&r,NULL,1,resolve,count_wake);assert(count[19]==1);
    pes27_notify(&r,&objects[1],0,resolve,count_wake);assert(count[19]==2);
    for(unsigned i=0;i<20;++i)pes27_unregister(&r,&ws[(i*7)%20]);
    assert(!r.head && r.notified+r.filtered==r.candidates);
    init_handles();
}

#define NTHREADS 8
#define ROUNDS 2000
static pthread_mutex_t mutex=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t ready_cond=PTHREAD_COND_INITIALIZER;
static struct pes27_router router;
static unsigned ready, consumed[NTHREADS];
static int tokens[NTHREADS];
static void *consumer(void *arg)
{
    unsigned id=(unsigned)(uintptr_t)arg;
    pthread_cond_t cond=PTHREAD_COND_INITIALIZER;
    struct pes27_interest in={.handles={id+1},.count=1};
    struct pes27_waiter w={.interest=&in,.condition=&cond};
    pthread_mutex_lock(&mutex);++ready;pthread_cond_broadcast(&ready_cond);
    for(unsigned n=0;n<ROUNDS;++n) {
        while(!tokens[id]) {
            pes27_register(&router,&w);
            /* An infinite wait makes a lost relevant notification fail the
             * subprocess watchdog instead of being hidden by a polling tick. */
            assert(!pthread_cond_wait(&cond,&mutex));
            pes27_unregister(&router,&w);
        }
        --tokens[id];++consumed[id];pthread_cond_broadcast(&ready_cond);
    }
    pthread_mutex_unlock(&mutex);pthread_cond_destroy(&cond);return NULL;
}
static void concurrent(void)
{
    pthread_t threads[NTHREADS];
    for(unsigned i=0;i<NTHREADS;++i)assert(!pthread_create(&threads[i],NULL,consumer,(void*)(uintptr_t)i));
    pthread_mutex_lock(&mutex);
    while(ready<NTHREADS)assert(!pthread_cond_wait(&ready_cond,&mutex));
    for(unsigned round=1;round<=ROUNDS;++round) {
        for(unsigned i=0;i<NTHREADS;++i) {
            ++tokens[i];pes27_notify(&router,&objects[i+1],1,resolve,signal_wake);
        }
        for(unsigned i=0;i<NTHREADS;++i)
            while(consumed[i]<round)assert(!pthread_cond_wait(&ready_cond,&mutex));
    }
    pthread_mutex_unlock(&mutex);
    for(unsigned i=0;i<NTHREADS;++i)assert(!pthread_join(threads[i],NULL));
    assert(!router.head && router.filtered && router.notified+router.filtered==router.candidates);
    /* Timed removal must leave no stale stack entry for later notifications. */
    pthread_cond_t cond=PTHREAD_COND_INITIALIZER;
    struct pes27_waiter w={.condition=&cond};struct timespec ts;
    pthread_mutex_lock(&mutex);pes27_register(&router,&w);clock_gettime(CLOCK_REALTIME,&ts);
    assert(pthread_cond_timedwait(&cond,&mutex,&ts)==ETIMEDOUT);
    pes27_unregister(&router,&w);pes27_notify(&router,NULL,1,resolve,signal_wake);
    assert(!router.head);pthread_mutex_unlock(&mutex);pthread_cond_destroy(&cond);
}
int main(void)
{
    init_handles();decoding();routing();concurrent();
    puts("PERF27: wire layouts, aliases, close, pseudo-handles, wait-all interests, broad fallback, 16,000 concurrent handoffs and timeout cleanup PASS");
    puts("routing workload: 2,000,000 candidates, 100,000 targeted notification attempts (95% fewer); not a game FPS benchmark");
}
