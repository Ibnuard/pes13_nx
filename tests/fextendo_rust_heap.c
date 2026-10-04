/* Real shared CPU mappings + allocation contract, not a shader/GPU test. */
#define main scratch_fixture_main
#include "fextendo_scratch_pages.c"
#undef main
struct normal_block {void *p;size_t n,a;};
static struct normal_block normal[256];
static size_t fast_limit=65536;
static unsigned failures;
static void wine_failure(unsigned kind,size_t n,size_t a,size_t old,uintptr_t caller){
    assert(kind&&n&&a);(void)old;(void)caller;__atomic_add_fetch(&failures,1,__ATOMIC_RELAXED);
}
void wine_nx_crash_rust_allocation(unsigned k,size_t n,size_t a,size_t o,uintptr_t c){wine_failure(k,n,a,o,c);}
static struct normal_block *normal_find(void *p){
    for(unsigned i=0;i<256;i++)if(normal[i].p==p)return &normal[i];
    assert(0&&"Alias or foreign pointer passed to original Rust allocator");return NULL;
}
void *fx_rust_real_alloc(size_t n,size_t a){
    if(n>fast_limit)return NULL;
    void *p=NULL;assert(n&&a&&!(a&(a-1)));
    assert(!posix_memalign(&p,a<sizeof(void *)?sizeof(void *):a,n));
    pthread_mutex_lock(&alloc_lock);
    unsigned i;for(i=0;i<256;i++)if(!normal[i].p)break;assert(i<256);
    normal[i]=(struct normal_block){p,n,a};pthread_mutex_unlock(&alloc_lock);return p;
}
void fx_rust_real_dealloc(void *p,size_t n,size_t a){
    pthread_mutex_lock(&alloc_lock);struct normal_block *b=normal_find(p);
    assert(b->n==n&&b->a==a);*b=(struct normal_block){0};pthread_mutex_unlock(&alloc_lock);free(p);
}
void *fx_rust_real_realloc(void *old,size_t old_n,size_t a,size_t n){
    void *p=fx_rust_real_alloc(n,a);if(!p)return NULL;
    memcpy(p,old,n<old_n?n:old_n);fx_rust_real_dealloc(old,old_n,a);return p;
}
void *fx_rust_real_alloc_zeroed(size_t n,size_t a){void *p=fx_rust_real_alloc(n,a);if(p)memset(p,0,n);return p;}
#include "../src/runtime/fextendo_rust_heap.h"
static void normal_empty(void){for(unsigned i=0;i<256;i++)assert(!normal[i].p);empty();}
static void *rust_worker(void *arg){
    unsigned char v=(uintptr_t)arg;void *p=pes13_rust_alloc(131077,64);assert(p);contents(p,131077,v);
    pthread_barrier_wait(&barrier);
    for(unsigned i=0;i<131077;i+=4096)assert(((unsigned char *)p)[i]==v);
    pes13_rust_dealloc(p,131077,64);return NULL;
}
int main(void){
    for(size_t a=1;a<=4096;a*=2){
        void *p=pes13_rust_alloc(123,a);assert(p&&!((uintptr_t)p%a));contents(p,123,0x81);
        p=pes13_rust_realloc(p,123,a,321);assert(p&&((unsigned char *)p)[122]==0x81);
        pes13_rust_dealloc(p,321,a);normal_empty();
    }
    assert(!fx_rust_heap_stats[0]);
    const size_t alignments[]={1,16,64,4096,65536,2*1024*1024};
    limit=12288;
    for(unsigned i=0;i<sizeof(alignments)/sizeof(alignments[0]);i++){
        size_t a=alignments[i];void *p=pes13_rust_alloc(131077,a);assert(p&&pes13_cpu_pages_owned(p)&&!((uintptr_t)p%a));
        contents(p,131077,0x9a);pes13_rust_dealloc(p,131077,a);normal_empty();
    }
    void *p=pes13_rust_alloc_zeroed(131077,64);assert(p);
    for(unsigned i=0;i<131077;i++)assert(!((unsigned char *)p)[i]);
    contents(p,131077,0x77);
    void *q=pes13_rust_realloc(p,131077,64,262177);assert(q&&q!=p);
    for(unsigned i=0;i<131077;i++)assert(((unsigned char *)q)[i]==0x77);
    p=pes13_rust_realloc(q,262177,64,32768);assert(p&&!pes13_cpu_pages_owned(p));
    assert(((unsigned char *)p)[32767]==0x77);
    q=pes13_rust_realloc(p,32768,64,262177);assert(q&&pes13_cpu_pages_owned(q));
    assert(((unsigned char *)q)[32767]==0x77);
    remaining=0;assert(!pes13_rust_realloc(q,262177,64,524301));
    assert(((unsigned char *)q)[32767]==0x77&&pes13_cpu_pages_owned(q)&&failures==1);
    remaining=~0u;pes13_rust_dealloc(q,262177,64);normal_empty();
    fail_map=map_calls+2;assert(!pes13_rust_alloc(131077,64));fail_map=0;normal_empty();
    assert(!pes13_cpu_pages_allocate(SIZE_MAX,16)&&!pes13_cpu_pages_allocate(10,3));normal_empty();
    pthread_t threads[8];pthread_barrier_init(&barrier,NULL,8);
    for(uintptr_t i=0;i<8;i++)assert(!pthread_create(&threads[i],NULL,rust_worker,(void *)(i+1)));
    for(unsigned i=0;i<8;i++)assert(!pthread_join(threads[i],NULL));
    pthread_barrier_destroy(&barrier);normal_empty();
    p=pes13_rust_alloc(131077,65536);assert(p);fail_unmap=unmap_calls+1;
    pes13_rust_dealloc(p,131077,65536);assert(pes13_cpu_pages_owned(p)&&fx_sp_stats[10]==1);
    /* Modeled process teardown only; runtime deliberately retains ownership. */
    fail_unmap=0;for(unsigned i=0;i<FX_SP_SLOTS;i++)if(fx_sp_slots[i].state==FX_SP_QUARANTINE)assert(fx_sp_dispose(&fx_sp_slots[i]));
    normal_empty();
    puts("PASS: native fast path, fragmented CPU fallback, 1-byte to 2-MiB alignment, zeroing, both realloc directions, failure preserves old bytes, eight concurrent owners, rollback and unmap quarantine");
    return 0;
}
