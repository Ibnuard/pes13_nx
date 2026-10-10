/* Repeated asset handoffs with leftover writer endpoints, under a fixed budget.
 * The budget models allocator pressure; real pipe code and pthread locks run. */
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
struct allocation { void *p;size_t n; };
static struct allocation blocks[8192];
static size_t held,peak,budget=8*1024*1024;
static unsigned fail_at,calls;
static void *tracked_malloc(size_t n) {
    calls++;
    if((fail_at&&calls==fail_at)||n>budget-held)return NULL;
    void *p=malloc(n);assert(p);
    for(unsigned i=0;i<8192;i++)if(!blocks[i].p){
        blocks[i]=(struct allocation){p,n};held+=n;if(held>peak)peak=held;return p;
    }
    abort();
}
static void *tracked_calloc(size_t n,size_t s) {
    assert(!s||n<=SIZE_MAX/s);void *p=tracked_malloc(n*s);if(p)memset(p,0,n*s);return p;
}
static void tracked_free(void *p) {
    if(!p)return;
    for(unsigned i=0;i<8192;i++)if(blocks[i].p==p){held-=blocks[i].n;blocks[i].p=NULL;free(p);return;}
    abort();
}
#define malloc tracked_malloc
#define calloc tracked_calloc
#define free tracked_free
#include "horizon_anon_pipe.h"
#undef malloc
#undef calloc
#undef free
int main(void) {
    struct fxap_pipe *writers[1200];unsigned completed=0,n;
    unsigned quota=2101740,length=1050870;
    unsigned char *payload=malloc(length),*readback=malloc(length);assert(payload&&readback);
    for(unsigned i=0;i<length;i++)payload[i]=(i*17u+i/67u)&255;
    for(unsigned i=0;i<1200;i++) {
        struct fxap_pipe *p=fxap_create(quota);
        if(!p)break;
        assert(!fxap_write(p,payload,length,&n)&&n==length);
        /* AFSIO may replace an unread BIN, or finish consuming it. */
        if(i%3==2){assert(!fxap_read(p,readback,length,&n)&&n==length);assert(!memcmp(payload,readback,length));}
        fxap_close(p,0); /* The sole reader closes; writer intentionally stays. */
        assert(fxap_write(p,payload,1,&n)==FXAP_BROKEN&&!n);
        writers[completed++]=p;
#ifndef BASELINE
        assert(held==(i+1)*sizeof(*p));
        assert(!fxap_metrics[FXAP_BYTES]);
#endif
    }
#ifdef BASELINE
    assert(completed==3&&held>6*1024*1024);
    printf("PASS baseline: Kit13 exhausts 8 MiB after %u leftover writers; held=%zu\n",completed,held);
#else
    assert(completed==1200&&peak<3*1024*1024);
    printf("PASS candidate: %u complete handoffs; held=%zu peak=%zu; all closed-reader buffers reclaimed\n",completed,held,peak);
#endif
    for(unsigned i=0;i<completed;i++){fxap_close(writers[i],1);fxap_destroy(writers[i]);}
    assert(!held);
#ifndef BASELINE
    assert(!fxap_metrics[FXAP_LIVE]&&!fxap_metrics[FXAP_BYTES]);
    assert(fxap_metrics[FXAP_RECLAIMED]==(uint64_t)completed*quota);
    /* Metadata and buffer failures each roll back without retained allocations. */
    for(unsigned step=1;step<=2;step++) {
        calls=0;fail_at=step;assert(!fxap_create(quota)&&!held);
    }
    fail_at=0;assert(!fxap_create(UINT_MAX)&&!held);
    struct fxap_pipe *p=fxap_create(quota);assert(p);
    assert(!fxap_write(p,payload,length,&n)&&n==length);fxap_close(p,1);
    assert(!fxap_read(p,readback,length,&n)&&n==length&&!memcmp(payload,readback,length));
    assert(fxap_read(p,readback,1,&n)==FXAP_BROKEN&&!n);
    fxap_close(p,0);fxap_close(p,0);fxap_destroy(p);assert(!held);
    puts("PASS allocation failures, idempotent reader close and writer-close buffered drain");
#endif
    free(payload);free(readback);return 0;
}
