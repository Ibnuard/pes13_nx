/* Real pthread reproduction: Kitserver writes size bytes into a size*2 pipe
 * BEFORE publishing the read handle. No concurrent consumer can rescue it. */
#include <assert.h>
#include <limits.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

static int deny_allocation;
static size_t requested_allocation;
static void *quota_calloc(size_t count,size_t size) {
    requested_allocation=count*size;
    return deny_allocation?NULL:calloc(count,size);
}
#define calloc quota_calloc
#include "horizon_anon_pipe.h"
#undef calloc

struct writer {
    struct fxap_pipe *pipe;
    unsigned char *bytes;
    unsigned count,status,done;
    atomic_uint finished;
};
static void *write_before_publish(void *arg) {
    struct writer *w=arg;
    w->status=fxap_write(w->pipe,w->bytes,w->count,&w->done);
    atomic_store(&w->finished,1);
    return NULL;
}
static int wait_completed(struct writer *w) {
    const struct timespec delay={0,1000000};
    for(unsigned i=0;i<1000&&!atomic_load(&w->finished);i++)nanosleep(&delay,NULL);
    return atomic_load(&w->finished);
}
static void handoff(unsigned quota,unsigned length,int old) {
    struct fxap_pipe *p=fxap_create(quota);assert(p);
    struct writer w={.pipe=p,.count=length};
    w.bytes=malloc(length);assert(w.bytes);
    for(unsigned i=0;i<length;i++)w.bytes[i]=(i*17u+i/67u)&255;
    pthread_t thread;assert(!pthread_create(&thread,NULL,write_before_publish,&w));
    int completed=wait_completed(&w);
    if(old) {
        assert(!completed&&p->capacity==1048576);
        pthread_mutex_lock(&p->lock);assert(p->used==1048576);pthread_mutex_unlock(&p->lock);
        fxap_close(p,0); /* Cancel the reproduced stall; no synthetic consumer. */
        assert(!pthread_join(thread,NULL)&&w.status==FXAP_BROKEN&&w.done==1048576);
    } else {
        assert(completed&&p->capacity==(quota?quota:4096));
        assert(!pthread_join(thread,NULL)&&!w.status&&w.done==length);
        /* Only now is the pipe passed to the game, as in kservGetFileInfo. */
        unsigned char buffer[8191];unsigned n;
        for(unsigned pos=0;pos<length;) {
            assert(!fxap_read(p,buffer,sizeof(buffer),&n)&&n>0);
            assert(!memcmp(buffer,w.bytes+pos,n));pos+=n;
        }
        /* Reuse a nonzero head, cross wrap, close then drain buffered data. */
        assert(!fxap_write(p,w.bytes,length,&n)&&n==length);
        fxap_close(p,1);
        for(unsigned pos=0;pos<length;) {
            assert(!fxap_read(p,buffer,sizeof(buffer),&n)&&n>0);
            assert(!memcmp(buffer,w.bytes+pos,n));pos+=n;
        }
        assert(fxap_read(p,buffer,1,&n)==FXAP_BROKEN&&!n);
        fxap_close(p,0);
    }
    fxap_destroy(p);free(w.bytes);
}
int main(void) {
#ifdef BASELINE
    handoff(2101740,1050870,1);
    puts("PASS baseline reproduction: Kit12 truncates 2101740 to 1048576; serial 1050870-byte writer blocks with 2294 bytes remaining");
#else
    const unsigned quotas[]={0,64,1048575,1048576,1048577,2101740,8*1024*1024+34};
    for(unsigned i=0;i<sizeof(quotas)/sizeof(quotas[0]);i++) {
        unsigned capacity=quotas[i]?quotas[i]:4096;
        handoff(quotas[i],capacity/2,0);
    }
    handoff(2101740,2101740,0); /* A full requested quota fits before any reader. */
    assert(fxap_advance(UINT_MAX-3,10,UINT_MAX)==7);
    assert(fxap_advance(UINT_MAX-3,UINT_MAX,UINT_MAX)==UINT_MAX-3);
    assert(fxap_advance(0,UINT_MAX,UINT_MAX)==0);
    deny_allocation=1;
    assert(!fxap_create(2101740));
    assert(!fxap_create(UINT_MAX)); /* Never fake success with a smaller quota. */
    puts("PASS candidate: 8 serial handoffs (default to 8 MiB), exact device size, full quota, wrap/drain, overflow-safe indices and allocation failure");
#endif
    return 0;
}
