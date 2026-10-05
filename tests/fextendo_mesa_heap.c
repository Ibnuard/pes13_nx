/* Exercise real C fallback mappings and native realloc/free contracts. */
#define FX_TEST_VA_REUSE 1
#define main scratch_fixture_main
#include "fextendo_scratch_pages.c"
#undef main
#include <malloc.h>
static size_t normal_limit=65536;
static void *normal_malloc(size_t n){return n<=normal_limit?malloc(n):NULL;}
static void *normal_realloc(void *p,size_t n){assert(!pes13_cpu_pages_owned(p));return n<=normal_limit?realloc(p,n):NULL;}
static void normal_free(void *p){assert(!p||!pes13_cpu_pages_owned(p));free(p);}
size_t wine_nx_release_idle_backing_pages(void){return 0;}
#define malloc normal_malloc
#define realloc normal_realloc
#define free normal_free
#include "../src/runtime/fextendo_mesa_heap.h"
#undef free
#undef realloc
#undef malloc
static void *mesa_worker(void *arg){
    unsigned char v=(uintptr_t)arg;
    for(unsigned i=0;i<30;i++){
        size_t n=90192+i*317;
        void *p=pes13_mesa_malloc(n);assert(p);contents(p,n,v);
        void *q=pes13_mesa_realloc(p,n*2+3);assert(q);
        for(size_t at=0;at<n;at+=4096)assert(((unsigned char *)q)[at]==v);
        pes13_mesa_free(q);
    }
    return NULL;
}
static void *retired_address;
static unsigned reused;
static void reissue_during_retirement(void){
    /* Old owner still occupies its metadata slot while the virtual address
     * has become allocatable. Simulate the other thread at this exact point. */
    void *p=pes13_mesa_malloc(90192);assert(p==retired_address);
    contents(p,90192,0x71);pes13_mesa_free(p);reused++;
}
int main(void){
    setvbuf(stdout,NULL,_IONBF,0);
    const size_t sizes[]={1,47,90192,135177,1048583,17*1024*1024+31};
    for(unsigned i=0;i<sizeof(sizes)/sizeof(*sizes);i++){
        size_t n=sizes[i];printf("size %zu\n",n);void *p=pes13_mesa_malloc(n);assert(p);contents(p,n,0x56);
        assert(!((uintptr_t)p%16));pes13_mesa_free(p);empty();
    }
    limit=12288;
    puts("realloc transitions");
    void *p=pes13_mesa_malloc(32768);assert(p);contents(p,32768,0x37);
    void *q=pes13_mesa_realloc(p,90192);assert(q&&pes13_cpu_pages_owned(q));
    assert(((unsigned char *)q)[32767]==0x37);contents(q,90192,0x56);
    remaining=0;assert(!pes13_mesa_realloc(q,180177));
    assert(((unsigned char *)q)[90191]==0x56&&pes13_cpu_pages_size(q)==90192);
    remaining=~0u;p=pes13_mesa_realloc(q,180177);assert(p&&((unsigned char *)p)[90191]==0x56);
    q=pes13_mesa_realloc(p,8192);assert(q&&!pes13_cpu_pages_owned(q)&&((unsigned char *)q)[8191]==0x56);
    assert(!pes13_mesa_realloc(q,0));empty();
    assert(!pes13_mesa_malloc(SIZE_MAX));pes13_mesa_free(NULL);empty();
    fail_map=map_calls+2;assert(!pes13_mesa_malloc(90192));fail_map=0;empty();
    p=pes13_mesa_malloc(90192);assert(p);retired_address=p;
    reuse_on_release=1;after_vm_unlock=reissue_during_retirement;
    pes13_mesa_free(p);assert(reused==1);empty();
    puts("same-address reissue before old metadata teardown passed");
    puts("concurrency");
    pthread_t ids[8];
    for(uintptr_t i=0;i<8;i++)assert(!pthread_create(&ids[i],NULL,mesa_worker,(void *)(i+1)));
    for(unsigned i=0;i<8;i++)assert(!pthread_join(ids[i],NULL));empty();
    p=pes13_mesa_malloc(90192);assert(p);fail_unmap=unmap_calls+1;
    puts("quarantine");
    pes13_mesa_free(p);assert(pes13_cpu_pages_owned(p));
    fail_unmap=0;for(unsigned i=0;i<FX_SP_SLOTS;i++)if(fx_sp_slots[i].state==FX_SP_QUARANTINE)assert(fx_sp_dispose(&fx_sp_slots[i]));
    empty();
    puts("PASS Mesa CPU heap: real shared mappings, arbitrary sizes, native/alias realloc, failed-growth preservation, recursive-free building blocks, eight concurrent workers and quarantine");
}
