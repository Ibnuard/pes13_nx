/* The real generated native callbacks, with only malloc/aligned_alloc failure
 * injected. Exercise shared compiler/container ownership under ASan/UBSan. */
#include "horizon_host.h"
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#define MIB (1024u*1024u)
extern void pes13_fex_scratch_snapshot(uint64_t out[16]);
void *__real_malloc(size_t);
void *__real_aligned_alloc(size_t,size_t);
void __real_free(void *);
static int pressure;
static uintptr_t arena;
static const struct pes13_fex_host *host;
void *__wrap_malloc(size_t n){if(pressure){errno=ENOMEM;return NULL;}return __real_malloc(n);}
void *__wrap_aligned_alloc(size_t a,size_t n){if(pressure){errno=ENOMEM;return NULL;}return __real_aligned_alloc(a,n);}
void __wrap_free(void *p){assert(!p||(uintptr_t)p<arena||(uintptr_t)p>=arena+64*MIB);__real_free(p);}
static void fill(unsigned char *p,size_t n,unsigned v){assert(p);memset(p,v,n);assert(p[0]==v&&p[n-1]==v);}
static void *worker(void *arg){
    unsigned v=(uintptr_t)arg;
    for(unsigned i=0;i<500;i++){
        size_t n=1+(i*317+v*23)%65536,a=(size_t)16<<(i%9);
        unsigned char *p=host->allocate_heap(n,a);assert(p&&!((uintptr_t)p&(a-1)));
        fill(p,n,v);host->release_heap(p);
    }
    return NULL;
}
int main(void){
    host=pes13_fex_native_host();
    void *probe=host->allocate_scratch(8*MIB);assert(probe);arena=(uintptr_t)probe;host->release_scratch(probe);
    unsigned char *old=host->allocate_heap(5*MIB,16);fill(old,5*MIB,0x35);
    void *compiler=host->allocate_scratch(16*MIB);fill(compiler,16*MIB,0x16);
    pressure=1;
    unsigned char *next=host->allocate_heap(10*MIB,16);assert(next);
    memcpy(next,old,5*MIB);assert(next[5*MIB-1]==0x35);
    memset(next+5*MIB,0x42,5*MIB);assert(next[10*MIB-1]==0x42);
    host->release_heap(old);host->release_heap(next);
    assert(((unsigned char *)compiler)[16*MIB-1]==0x16);
    /* Many tiny allocations share pages, not an entire 8-MiB compiler unit. */
    void *small[256];for(unsigned i=0;i<256;i++){small[i]=host->allocate_heap(17,64);fill(small[i],17,0x17);}
    uint64_t stats[16];pes13_fex_scratch_snapshot(stats);assert(stats[1]==17*MIB);
    for(unsigned i=0;i<256;i++){assert(((unsigned char *)small[i])[16]==0x17);host->release_heap(small[i]);}
    /* No overlap, stealing or page-alias dependencies between families. */
    pthread_t threads[8];for(uintptr_t i=0;i<8;i++)assert(!pthread_create(&threads[i],NULL,worker,(void *)(i+1)));
    for(unsigned i=0;i<8;i++)assert(!pthread_join(threads[i],NULL));
    void *look=host->allocate_scratch(MIB);fill(look,MIB,0x56);host->release_scratch(look);
    pes13_fex_scratch_snapshot(stats);assert(stats[1]==16*MIB&&stats[2]==1);
    void *rest=host->allocate_scratch(48*MIB);assert(rest);
    assert(!host->allocate_heap(10*MIB,16));assert(((unsigned char *)compiler)[16*MIB-1]==0x16);
    assert(!host->allocate_heap(UINT64_MAX,16)&&!host->allocate_heap(17,24));
    host->release_scratch(rest);host->release_scratch(compiler);
    pes13_fex_scratch_snapshot(stats);assert(!stats[1]&&!stats[2]&&stats[9]==64*MIB);
    pressure=0;
    puts("PASS shared pressure reserve: 5-to-10 MiB growth, 256 small owners, 4000 concurrent transfers, live compiler preservation, true exhaustion and complete return");
}
