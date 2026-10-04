/* Actual native host adapter with allocation pressure injected at libc only. */
#include "horizon_host.h"
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define BLOCK (8u*1024u*1024u)
extern void pes13_fex_scratch_snapshot(uint64_t out[8]);
void *__real_aligned_alloc(size_t,size_t);
void __real_free(void *);
static int bootstrap=1,budget=4,deny_large,attempts,free_count;
void *__wrap_aligned_alloc(size_t a,size_t n){
    if(n==BLOCK){
        if(bootstrap&&attempts++>=budget){errno=ENOMEM;return NULL;}
        if(__atomic_load_n(&deny_large,__ATOMIC_RELAXED)){errno=ENOMEM;return NULL;}
    }
    return __real_aligned_alloc(a,n);
}
void __wrap_free(void *p){if(p)__atomic_add_fetch(&free_count,1,__ATOMIC_RELAXED);__real_free(p);}
static const struct pes13_fex_host *host;
static pthread_mutex_t check_lock=PTHREAD_MUTEX_INITIALIZER;
static void *active[4];
static void *worker(void *arg){
    size_t id=(size_t)arg;
    for(unsigned i=0;i<1000;i++){
        unsigned char *p=host->allocate_scratch(BLOCK);assert(p);
        pthread_mutex_lock(&check_lock);
        for(unsigned j=0;j<4;j++)assert(active[j]!=p);
        active[id]=p;pthread_mutex_unlock(&check_lock);
        p[0]=(unsigned char)id;p[BLOCK-1]=(unsigned char)(id+11);
        assert(p[0]==id&&p[BLOCK-1]==id+11);
        pthread_mutex_lock(&check_lock);active[id]=NULL;pthread_mutex_unlock(&check_lock);
        host->release_scratch(p);
    }
    return NULL;
}
int main(int argc,char **argv){
    assert(argc==2);budget=atoi(argv[1]);assert(budget==0||budget==2||budget==4);
    host=pes13_fex_native_host();bootstrap=0;
    uint64_t stats[8];pes13_fex_scratch_snapshot(stats);
    assert(stats[0]==(unsigned)budget&&stats[1]==0&&stats[7]==(budget<4));
    assert(pes13_fex_native_host()==host);
    assert(!host->allocate_scratch(0)&&!host->allocate_scratch(UINT64_MAX));
    host->release_scratch(NULL);
    void *small=host->allocate_scratch(17);assert(small&&!((uintptr_t)small&4095));
    int frees=free_count;host->release_scratch(small);assert(free_count==frees+1);
    deny_large=1;
    assert(!__wrap_aligned_alloc(4096,BLOCK)); /* old allocation path fails */
    void *blocks[4];
    for(int i=0;i<budget;i++){
        blocks[i]=host->allocate_scratch(BLOCK);assert(blocks[i]&&!((uintptr_t)blocks[i]&4095));
        for(int j=0;j<i;j++)assert(blocks[i]!=blocks[j]);
        memset(blocks[i],i+1,BLOCK);
    }
    assert(!host->allocate_scratch(BLOCK)); /* no stealing a busy slot */
    for(int i=0;i<budget;i++){
        unsigned char *p=blocks[i];assert(p[0]==i+1&&p[BLOCK-1]==i+1);
    }
    frees=free_count;
    for(int i=0;i<budget;i++)host->release_scratch(blocks[i]);
    assert(free_count==frees);
    if(budget){
        pthread_t workers[4];
        for(int i=0;i<budget;i++)assert(!pthread_create(&workers[i],NULL,worker,(void *)(size_t)i));
        for(int i=0;i<budget;i++)assert(!pthread_join(workers[i],NULL));
    }
    pes13_fex_scratch_snapshot(stats);assert(stats[1]==0&&stats[5]==(unsigned)budget);
    deny_large=0;
    for(int i=0;i<budget;i++)blocks[i]=host->allocate_scratch(BLOCK);
    void *overflow=host->allocate_scratch(BLOCK);assert(overflow);
    frees=free_count;host->release_scratch(overflow);assert(free_count==frees+1);
    for(int i=0;i<budget;i++)host->release_scratch(blocks[i]);
    printf("PASS scratch reserve %d slots: pressure, exhaustion, content, ownership/reuse, fallback and concurrency\n",budget);
}
