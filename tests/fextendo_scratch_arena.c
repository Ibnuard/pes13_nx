/* Native callback contract under fragmented-heap pressure, with real memory.
 * Only libc allocation failure is injected; the adapter is unmodified here. */
#include "horizon_host.h"
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define UNIT (8u * 1024u * 1024u)
#ifndef FX_SCRATCH_TEST_UNITS
#define FX_SCRATCH_TEST_UNITS 4u
#endif
extern void pes13_fex_scratch_snapshot(uint64_t out[16]);
void *__real_aligned_alloc(size_t,size_t);
void __real_free(void *);
static int bootstrap=1, budget, deny_large, attempts, free_count;
void *__wrap_aligned_alloc(size_t a,size_t n) {
    if (bootstrap) attempts++;
    if ((bootstrap && n>(size_t)budget*UNIT) ||
        (__atomic_load_n(&deny_large,__ATOMIC_RELAXED) && n>=UNIT)) {
        errno=ENOMEM;return NULL;
    }
    return __real_aligned_alloc(a,n);
}
void __wrap_free(void *p) {
    if (p) __atomic_add_fetch(&free_count,1,__ATOMIC_RELAXED);
    __real_free(p);
}
static const struct pes13_fex_host *host;
static pthread_mutex_t check_lock=PTHREAD_MUTEX_INITIALIZER;
static struct {uintptr_t begin,end;} active[4];
static void *worker(void *arg) {
    size_t id=(size_t)arg;
    for (unsigned i=0;i<700;i++) {
        /* Four workers need at most 32 MiB in either configuration. */
        size_t size=(id&1)?2*UNIT:UNIT;
        unsigned char *p=host->allocate_scratch(size);
        if (!p) { /* other workers may temporarily occupy adjacent units */
            p=host->allocate_scratch(UNIT);size=UNIT;
        }
        assert(p);
        pthread_mutex_lock(&check_lock);
        for (unsigned j=0;j<4;j++)
            assert(!active[j].begin || (uintptr_t)p+size<=active[j].begin || (uintptr_t)p>=active[j].end);
        active[id].begin=(uintptr_t)p;active[id].end=(uintptr_t)p+size;
        pthread_mutex_unlock(&check_lock);
        p[0]=(unsigned char)id;p[size-1]=(unsigned char)(id+11);
        assert(p[0]==id && p[size-1]==id+11);
        pthread_mutex_lock(&check_lock);active[id].begin=active[id].end=0;pthread_mutex_unlock(&check_lock);
        host->release_scratch(p);
    }
    return NULL;
}
static void check_empty(size_t capacity) {
    uint64_t stats[16];pes13_fex_scratch_snapshot(stats);
    assert(stats[0]==capacity && !stats[1] && !stats[2] && stats[9]==capacity);
}
int main(int argc,char **argv) {
    assert(argc==2);budget=atoi(argv[1]);assert(budget==0||budget==1||budget==2||budget==4||budget==8);
    assert((unsigned)budget<=FX_SCRATCH_TEST_UNITS);
    host=pes13_fex_native_host();bootstrap=0;
    uint64_t stats[16];pes13_fex_scratch_snapshot(stats);
    unsigned expected_failures=0;
    for(unsigned units=FX_SCRATCH_TEST_UNITS;units>(unsigned)budget;units/=2)expected_failures++;
    assert(stats[0]==(unsigned)budget*UNIT && stats[8]==expected_failures);
    int tries=attempts;assert(pes13_fex_native_host()==host && attempts==tries);
    assert(!host->allocate_scratch(0) && !host->allocate_scratch(UINT64_MAX));
    host->release_scratch(NULL);
    void *small=host->allocate_scratch(17);assert(small && !((uintptr_t)small&4095));
    int frees=free_count;host->release_scratch(small);assert(free_count==frees+1);
    deny_large=1;
    assert(!__wrap_aligned_alloc(4096,2*UNIT)); /* frozen ordinary path fails */
    void *blocks[8];
    for (int i=0;i<budget;i++) {
        blocks[i]=host->allocate_scratch(UNIT);assert(blocks[i]);
        for (int j=0;j<i;j++) assert(blocks[i]!=blocks[j]);
        memset(blocks[i],i+1,UNIT);
    }
    assert(!host->allocate_scratch(UNIT)); /* never steal a live allocation */
    for (int i=0;i<budget;i++) {
        unsigned char *p=blocks[i];assert(p[0]==i+1 && p[UNIT-1]==i+1);
    }
    frees=free_count;
    for (int i=0;i<budget;i++) host->release_scratch(blocks[i]);
    assert(free_count==frees);check_empty((size_t)budget*UNIT);
    /* Reproduce the device sequence: release all four 8-MiB buffers, then
     * request 16 MiB under pressure. The old four-slot reserve failed here. */
    for (unsigned units=1;units<=(unsigned)budget;units++) {
        unsigned char *p=host->allocate_scratch(units*UNIT);assert(p);
        p[0]=42;p[units*UNIT-1]=99;assert(p[0]==42 && p[units*UNIT-1]==99);
        pes13_fex_scratch_snapshot(stats);assert(stats[1]==units*UNIT && stats[2]==1);
        host->release_scratch(p);check_empty((size_t)budget*UNIT);
    }
    if (budget>=4) {
        /* Fill the entire reserve; separated holes cannot be merged. */
        for (unsigned i=0;i<(unsigned)budget;i++) blocks[i]=host->allocate_scratch(UNIT);
        host->release_scratch(blocks[0]);host->release_scratch(blocks[2]);
        pes13_fex_scratch_snapshot(stats);assert(stats[1]==(budget-2)*UNIT && stats[9]==UNIT);
        assert(!host->allocate_scratch(2*UNIT)); /* two holes are not contiguous */
        host->release_scratch(blocks[1]);
        pes13_fex_scratch_snapshot(stats);assert(stats[9]==3*UNIT);
        unsigned char *p=host->allocate_scratch(3*UNIT);assert(p==blocks[0]);
        host->release_scratch(p+UNIT);host->release_scratch(p+4096);
        pes13_fex_scratch_snapshot(stats);assert(stats[1]==budget*UNIT && stats[2]==budget-2 && stats[15]==2);
        assert(!host->allocate_scratch(UNIT));
        host->release_scratch(p);
        for(unsigned i=3;i<(unsigned)budget;i++)host->release_scratch(blocks[i]);
        check_empty(budget*UNIT);
        /* Non-power-of-two workspace receives enough actual capacity. */
        p=host->allocate_scratch(UNIT+4096);assert(p);p[UNIT+4095]=7;
        pes13_fex_scratch_snapshot(stats);assert(stats[1]==2*UNIT);
        host->release_scratch(p);
        pthread_t workers[2]; /* 8+16 MiB can coexist, leaving a spare unit */
        for (size_t i=0;i<2;i++) assert(!pthread_create(&workers[i],NULL,worker,(void *)i));
        for (unsigned i=0;i<2;i++) assert(!pthread_join(workers[i],NULL));
        check_empty(budget*UNIT);
    }
    if(budget==8){
        /* Actual console overlap: a live 16-MiB buffer plus two live 8-MiB
         * buffers must not prevent a further 8-MiB compile under heap pressure. */
        unsigned char *held[4];size_t sizes[4]={2*UNIT,UNIT,UNIT,UNIT};
        for(unsigned i=0;i<4;i++){
            held[i]=host->allocate_scratch(sizes[i]);assert(held[i]);
            held[i][0]=i+10;held[i][sizes[i]-1]=i+20;
        }
        pes13_fex_scratch_snapshot(stats);assert(stats[1]==5*UNIT&&stats[2]==4);
        for(unsigned i=0;i<4;i++){
            assert(held[i][0]==i+10&&held[i][sizes[i]-1]==i+20);
            host->release_scratch(held[i]);
        }
        check_empty(budget*UNIT);
    }
    /* Empty reserve must not fake success for a larger unsupported request. */
    size_t beyond=(FX_SCRATCH_TEST_UNITS+1)*UNIT;
    assert(!host->allocate_scratch(beyond));
    pes13_fex_scratch_snapshot(stats);assert(stats[11]==beyond && stats[10]==beyond);
    deny_large=0;
    for (int i=0;i<budget;i++) blocks[i]=host->allocate_scratch(UNIT);
    void *fallback=host->allocate_scratch(2*UNIT);assert(fallback);
    for (int i=0;i<budget;i++) assert(fallback!=blocks[i]);
    frees=free_count;host->release_scratch(fallback);assert(free_count==frees+1);
    for (int i=0;i<budget;i++) host->release_scratch(blocks[i]);
    check_empty((size_t)budget*UNIT);
    printf("PASS scratch arena %d MiB: pressure, growth, holes/coalescing, concurrent live compiler overlap, ownership and fallback\n",budget*8);
}
