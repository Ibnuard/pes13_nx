#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int fail_heap;
static size_t live,freed;
static void *model_alloc(size_t a,size_t n){if(fail_heap)return NULL;void *p=aligned_alloc(a,n);assert(p);live++;return p;}
static void model_free(void *p){assert(p&&live);live--;freed++;free(p);}
#define aligned_alloc model_alloc
#define free model_free
#include "horizon_pool.h"
#include "horizon_pool_pressure.h"
#undef free
#undef aligned_alloc
int main(void){
    struct horizon_page_pool pool={0};
    void *a=horizon_pages_alloc(&pool,2*1024*1024);
    void *b=horizon_pages_alloc(&pool,4096);assert(a&&b&&live==2);
    memset(b,0x45,4096);
    assert(horizon_pages_free(&pool,a,2*1024*1024));
    assert(horizon_pages_trim(&pool)==2*1024*1024&&freed==1&&live==1);
    fail_heap=1;
    /* The first slot is now empty; later partially occupied arenas still
     * have reusable pages despite the forced system allocation failure. */
    void *c=horizon_pages_alloc(&pool,90112);assert(c&&live==1);
    memset(c,0x57,90112);assert(((unsigned char *)b)[4095]==0x45);
    assert(!horizon_pages_trim(&pool));
    assert(horizon_pages_free(&pool,c,90112)&&horizon_pages_free(&pool,b,4096));
    assert(horizon_pages_trim(&pool)==2*1024*1024&&!live);
    assert(!horizon_pages_alloc(&pool,4096));
    fail_heap=0;
    void *owners[32];for(unsigned i=0;i<32;i++){owners[i]=horizon_pages_alloc(&pool,2*1024*1024);assert(owners[i]);}
    for(unsigned i=0;i<32;i+=2)assert(horizon_pages_free(&pool,owners[i],2*1024*1024));
    assert(horizon_pages_trim(&pool)==32*1024*1024&&live==16);
    for(unsigned i=1;i<32;i+=2){memset(owners[i],(int)i,2*1024*1024);assert(horizon_pages_free(&pool,owners[i],2*1024*1024));}
    assert(horizon_pages_trim(&pool)==32*1024*1024&&!live);
    puts("PASS idle Wine arenas: exact 64-MiB cap, partial/live data retained, repeated trim/reuse, holes searched before new heap requests");
}
