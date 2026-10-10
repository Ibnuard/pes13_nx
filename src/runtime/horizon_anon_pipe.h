/* LGPL-2.1-or-later. In-process byte stream for Wine's synchronous CreatePipe.
 * No fd, SD file, socket, polling loop, or guest pointer is retained here. */
#ifndef HORIZON_ANON_PIPE_H
#define HORIZON_ANON_PIPE_H
#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define FXAP_BROKEN 0xc000014bu
#define FXAP_CANCELLED 0xc0000120u
#define FXAP_NO_MEMORY 0xc0000017u
enum { FXAP_CREATED, FXAP_LIVE, FXAP_BYTES, FXAP_PEAK, FXAP_RECLAIMED,
       FXAP_FAIL_META, FXAP_FAIL_BUFFER, FXAP_FAIL_SYNC, FXAP_METRICS };
static uint64_t fxap_metrics[FXAP_METRICS];
static void fxap_count(unsigned slot,uint64_t amount)
{
    __atomic_fetch_add(&fxap_metrics[slot],amount,__ATOMIC_RELAXED);
}
struct fxap_pipe {
    pthread_mutex_t lock;
    pthread_cond_t readable, writable;
    unsigned owners; /* Only the server object mutex protects ownership. */
    unsigned connected;
    unsigned capacity, head, used, read_open, write_open;
    unsigned char *bytes; /* Storage can go away before a leftover writer handle. */
};
static struct fxap_pipe *fxap_create(unsigned capacity)
{
    struct fxap_pipe *p;
    if (!capacity) capacity=4096;
    /* Kitserver writes a complete BIN before giving its read handle to PES.
     * A successful smaller buffer can deadlock that handoff. Honor the requested
     * quota or report allocation failure; never silently truncate it. */
    p=calloc(1,sizeof(*p));
    if (!p) { fxap_count(FXAP_FAIL_META,1);return NULL; }
    /* Only used bytes are ever exposed. Avoid clearing a multi-MiB quota that
     * WriteFile is about to fill, and keep its lifetime separate from handles. */
    p->bytes=malloc((size_t)capacity);
    if (!p->bytes) { fxap_count(FXAP_FAIL_BUFFER,1);free(p);return NULL; }
    if (pthread_mutex_init(&p->lock,NULL)) goto sync_failed;
    if (pthread_cond_init(&p->readable,NULL)) { pthread_mutex_destroy(&p->lock);goto sync_failed; }
    if (pthread_cond_init(&p->writable,NULL)) {
        pthread_cond_destroy(&p->readable);pthread_mutex_destroy(&p->lock);goto sync_failed;
    }
    p->capacity=capacity;p->read_open=p->write_open=p->owners=1;
    fxap_count(FXAP_CREATED,1);fxap_count(FXAP_LIVE,1);
    uint64_t held=__atomic_add_fetch(&fxap_metrics[FXAP_BYTES],capacity,__ATOMIC_RELAXED);
    uint64_t peak=__atomic_load_n(&fxap_metrics[FXAP_PEAK],__ATOMIC_RELAXED);
    while (held>peak&&!__atomic_compare_exchange_n(&fxap_metrics[FXAP_PEAK],&peak,held,0,
                                                   __ATOMIC_RELAXED,__ATOMIC_RELAXED)) {}
    return p;
sync_failed:
    fxap_count(FXAP_FAIL_SYNC,1);free(p->bytes);free(p);return NULL;
}
static void fxap_release_bytes(struct fxap_pipe *p)
{
    if (!p->bytes) return;
    free(p->bytes);p->bytes=NULL;p->head=p->used=0;
    __atomic_sub_fetch(&fxap_metrics[FXAP_BYTES],p->capacity,__ATOMIC_RELAXED);
}
static void fxap_destroy(struct fxap_pipe *p)
{
    pthread_cond_destroy(&p->readable);pthread_cond_destroy(&p->writable);
    pthread_mutex_destroy(&p->lock);fxap_release_bytes(p);
    __atomic_sub_fetch(&fxap_metrics[FXAP_LIVE],1,__ATOMIC_RELAXED);free(p);
}
static void fxap_close(struct fxap_pipe *p,int writer)
{
    pthread_mutex_lock(&p->lock);
    if (writer) p->write_open=0;
    else {
        p->read_open=0;
        /* Last reader only (the server accounts for duplicates). No future
         * read can observe queued bytes. Keep the writer handle valid and
         * report broken pipe on its next write, without retaining its quota. */
        if (p->bytes) fxap_count(FXAP_RECLAIMED,p->capacity);
        fxap_release_bytes(p);
    }
    pthread_cond_broadcast(&p->readable);pthread_cond_broadcast(&p->writable);
    pthread_mutex_unlock(&p->lock);
}
/* Both arguments are at most capacity. Subtraction avoids 32-bit sum wrap
 * for large DWORD quotas, without widening every read/write index. */
static unsigned fxap_advance(unsigned position,unsigned amount,unsigned capacity)
{
    unsigned remaining=capacity-position;
    return amount>=remaining?amount-remaining:position+amount;
}
static unsigned fxap_read(struct fxap_pipe *p,void *data,unsigned size,unsigned *done)
{
    unsigned first,n,status=0;
    *done=0;
    if (!size) return 0;
    pthread_mutex_lock(&p->lock);
    while (!p->used&&p->write_open&&p->read_open) pthread_cond_wait(&p->readable,&p->lock);
    if (!p->read_open) status=FXAP_CANCELLED;
    else if (!p->used) status=FXAP_BROKEN;
    else {
        n=size<p->used?size:p->used;
        first=n<p->capacity-p->head?n:p->capacity-p->head;
        memcpy(data,p->bytes+p->head,first);
        if (n>first) memcpy((unsigned char *)data+first,p->bytes,n-first);
        p->head=fxap_advance(p->head,n,p->capacity);p->used-=n;*done=n;
        pthread_cond_broadcast(&p->writable);
    }
    pthread_mutex_unlock(&p->lock);
    return status;
}
static unsigned fxap_write(struct fxap_pipe *p,const void *data,unsigned size,unsigned *done)
{
    unsigned status=0;
    *done=0;
    if (!size) return 0;
    pthread_mutex_lock(&p->lock);
    while (*done<size) {
        unsigned tail,n;
        while (p->used==p->capacity&&p->read_open&&p->write_open)
            pthread_cond_wait(&p->writable,&p->lock);
        if (!p->write_open) { status=FXAP_CANCELLED;break; }
        if (!p->read_open) { status=FXAP_BROKEN;break; }
        tail=fxap_advance(p->head,p->used,p->capacity);
        n=size-*done;
        if (n>p->capacity-p->used) n=p->capacity-p->used;
        if (n>p->capacity-tail) n=p->capacity-tail;
        memcpy(p->bytes+tail,(const unsigned char *)data+*done,n);
        p->used+=n;*done+=n;
        pthread_cond_broadcast(&p->readable);
    }
    pthread_mutex_unlock(&p->lock);
    return status;
}
#endif
