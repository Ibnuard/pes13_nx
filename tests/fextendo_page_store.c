/* Real shared Linux mappings model the kernel aliasing contract, not Horizon
 * scheduling or its SVC implementation. Allocator failures are deliberate. */
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

struct allocation { void *ptr; size_t size; int fd; };
static struct allocation allocations[8192];
static size_t limit = 1024*1024;
static int budget = -1, live_allocs;
static void *allocate_pages(size_t size) {
    if (size > limit || !budget) { errno = ENOMEM; return NULL; }
    if (budget > 0) --budget;
    unsigned i;
    for (i=0; i<8192 && allocations[i].ptr; ++i) {}
    assert(i<8192);
    int fd=memfd_create("pages",0); assert(fd>=0 && !ftruncate(fd,size));
    void *p=mmap(NULL,size,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0); assert(p!=MAP_FAILED);
    allocations[i]=(struct allocation){p,size,fd}; ++live_allocs;
    return p;
}
static struct allocation *find_allocation(void *ptr, size_t size) {
    for (unsigned i=0;i<8192;++i) {
        struct allocation *a=allocations+i;
        uintptr_t off=(uintptr_t)ptr-(uintptr_t)a->ptr;
        if(a->ptr && off<=a->size && size<=a->size-off) return a;
    }
    assert(!"unknown page storage"); return NULL;
}
static void release_pages(void *ptr,size_t size) {
    struct allocation *a=find_allocation(ptr,size);
    assert(ptr==a->ptr && size==a->size);
    assert(!munmap(ptr,size)); close(a->fd); a->ptr=NULL; --live_allocs;
}
#define HORIZON_MEMFILE_ALLOC_PAGES(n) allocate_pages(n)
#define HORIZON_MEMFILE_FREE_PAGES(p,n) release_pages(p,n)
#include "horizon_memfile.h"

static unsigned map_calls, fail_map, undo_calls, fail_undo;
static int map_piece(void *dst,void *src,size_t n,void *unused) {
    (void)unused;
    if (++map_calls==fail_map) { errno=EIO; return -1; }
    struct allocation *a=find_allocation(src,n);
    void *p=mmap(dst,n,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_FIXED,a->fd,(char*)src-(char*)a->ptr);
    assert(p==dst); return 0;
}
static int unmap_piece(void *dst,void *src,size_t n,void *unused) {
    (void)unused; (void)src;
    if (++undo_calls==fail_undo) { errno=EBUSY; return -1; }
    assert(mmap(dst,n,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED,-1,0)==dst); return 0;
}
static void *reserve(size_t n) {
    void *p=mmap(NULL,n,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0); assert(p!=MAP_FAILED); return p;
}
struct anchor_token { void *source,*view; size_t size; int fd; off_t offset; struct anchor_token *next; };
static struct anchor_token *anchors;
static unsigned anchor_calls, fail_anchor, unanchor_calls, fail_unanchor, alias_calls, fail_alias;
static void *anchor(void *source,size_t size,void **token) {
    if (++anchor_calls==fail_anchor) { errno=ENOMEM; return NULL; }
    struct allocation *a=find_allocation(source,size);
    struct anchor_token *t=calloc(1,sizeof(*t)); assert(t);
    t->source=source;t->size=size;t->fd=a->fd;t->offset=(char*)source-(char*)a->ptr;
    t->view=mmap(NULL,size,PROT_READ|PROT_WRITE,MAP_SHARED,a->fd,t->offset);assert(t->view!=MAP_FAILED);
    /* Access to locked physical pages must go through the anchor. */
    assert(!mprotect(source,size,PROT_NONE));
    t->next=anchors; anchors=t; *token=t; return t->view;
}
static int unanchor(void *view,void *source,size_t size,void *token) {
    if (++unanchor_calls==fail_unanchor) { errno=EBUSY; return -1; }
    struct anchor_token *t=token,**next=&anchors;
    assert(t->view==view && t->source==source && t->size==size);
    assert(!munmap(view,size) && !mprotect(source,size,PROT_READ|PROT_WRITE));
    while(*next!=t)next=&(*next)->next;
    *next=t->next;free(t);return 0;
}
static int alias(void *dst,void *src,size_t size) {
    if (++alias_calls==fail_alias) { errno=EIO; return -1; }
    for(struct anchor_token *t=anchors;t;t=t->next) {
        uintptr_t off=(uintptr_t)src-(uintptr_t)t->view;
        if(off<=t->size && size<=t->size-off) {
            assert(mmap(dst,size,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_FIXED,t->fd,t->offset+off)==dst);
            return 0;
        }
    }
    assert(!"alias outside anchor");return -1;
}
static int unalias(void *dst,void *src,size_t size) { return unmap_piece(dst,src,size,NULL); }
static const struct horizon_memfile_ops ops={anchor,unanchor,alias,unalias};

#ifndef TEST_BASELINE
static void test_backing(void) {
    const size_t size=5*1024*1024;
    struct horizon_page_store s;
    unsigned char *view=reserve(size), *second=reserve(size);
    assert(!horizon_store_alloc(&s,size,allocate_pages,release_pages));
    assert(!s.data && s.pieces);
    assert(!horizon_store_range(&s,view,0,size,map_piece,unmap_piece,NULL));
    assert(!horizon_store_range(&s,second,0,size,map_piece,unmap_piece,NULL));
    for(size_t i=0;i<size;i+=4096) { assert(!view[i]);view[i]=(unsigned char)(i/4096);assert(second[i]==view[i]); }
    /* Decommit crosses pieces, retains left/right views and physical contents. */
    size_t off=512*1024,n=3*1024*1024;
    assert(!horizon_store_range(&s,view+off,off,n,unmap_piece,map_piece,NULL));
    assert(!horizon_store_range(&s,view+off,off,n,map_piece,unmap_piece,NULL));
    assert(!memcmp(view,second,size));
    assert(!horizon_store_range(&s,view,0,size,unmap_piece,map_piece,NULL));
    assert(!horizon_store_range(&s,second,0,size,unmap_piece,map_piece,NULL));
    /* Mid-map failure: completed pieces are undone and original errno kept. */
    map_calls=undo_calls=0;fail_map=3;
    assert(horizon_store_range(&s,view,0,size,map_piece,unmap_piece,NULL)==-1 && errno==EIO);
    assert(undo_calls==2 && !s.poisoned);fail_map=0;
    assert(!horizon_store_range(&s,view,0,size,map_piece,unmap_piece,NULL));
    /* Failed partial unmap restores earlier pieces from the same backing. */
    undo_calls=map_calls=0;fail_undo=3;
    assert(horizon_store_range(&s,view,0,size,unmap_piece,map_piece,NULL)==-1 && errno==EBUSY);
    assert(map_calls==2 && !s.poisoned);fail_undo=0;
    for(size_t i=0;i<size;i+=4096) assert(view[i]==(unsigned char)(i/4096));
    assert(!horizon_store_range(&s,view,0,size,unmap_piece,map_piece,NULL));
    horizon_store_free(&s,release_pages);assert(!live_allocs);
    /* Progressive fragment sizes, complete rollback on allocation exhaustion. */
    limit=64*1024;budget=3;
    assert(horizon_store_alloc(&s,size,allocate_pages,release_pages)==-1 && errno==ENOMEM);
    assert(!live_allocs && !s.pieces && !s.data);budget=-1;
    assert(!horizon_store_alloc(&s,size,allocate_pages,release_pages));
    assert(!horizon_store_range(&s,view,0,size,map_piece,unmap_piece,NULL));
    assert(!horizon_store_range(&s,view,0,size,unmap_piece,map_piece,NULL));
    horizon_store_free(&s,release_pages);assert(!live_allocs);
    limit=32*1024*1024;
    assert(!horizon_store_alloc(&s,size,allocate_pages,release_pages) && s.data && !s.pieces);
    horizon_store_free(&s,release_pages);assert(!live_allocs);
    limit=1024*1024;
    /* Double kernel failure must quarantine, never free aliased storage. */
    assert(!horizon_store_alloc(&s,size,allocate_pages,release_pages));
    map_calls=undo_calls=0;fail_map=3;fail_undo=1;
    assert(horizon_store_range(&s,view,0,size,map_piece,unmap_piece,NULL)==-1 && s.poisoned);
    int before=live_allocs;horizon_store_free(&s,release_pages);assert(before==live_allocs);
    /* Explicit fixture teardown only, not production recovery. */
    fail_map=fail_undo=0;unmap_piece(view,s.pieces->data,s.pieces->size,NULL);
    s.poisoned=0;horizon_store_free(&s,release_pages);assert(!live_allocs);
    munmap(view,size);munmap(second,size);
    puts("PASS 5-MiB backing: fragmentation, shared pages, partial unmap, allocation rollback, OS rollback/quarantine, contiguous fast path");
}
#endif
static void test_memfile(void) {
    const size_t size=16*1024*1024;
    struct horizon_memfile *file=horizon_memfile_alloc(size,1,&ops);
#ifdef TEST_BASELINE
    assert(!file && errno==ENOMEM && !live_allocs);
    puts("PASS baseline reproduces 16-MiB section failure with fragmented heap");return;
#else
    assert(file && !file->pages.data && file->pages.pieces);
    unsigned char *v1=reserve(size),*v2=reserve(size),buf[96],readback[96];
    memset(buf,0x9c,sizeof(buf));
    size_t offset=1024*1024-32;
    assert(horizon_memfile_pwrite(file,(char*)buf,sizeof(buf),offset)==sizeof(buf));
    assert(!horizon_memfile_map(file,v1,0,size));
    assert(!horizon_memfile_map(file,v2,0,size));
    assert(!memcmp(v1+offset,buf,sizeof(buf)) && !memcmp(v2+offset,buf,sizeof(buf)));
    memset(v2+offset,0x41,sizeof(buf));
    assert(horizon_memfile_pread(file,(char*)readback,sizeof(readback),offset)==sizeof(readback));
    for(size_t i=0;i<sizeof(readback);++i)assert(readback[i]==0x41 && v1[offset+i]==0x41);
    unsigned long long range;int committed;
    assert(!horizon_memfile_committed_range(file,0,size,0,&range,&committed) && !committed && range==size);
    assert(!horizon_memfile_add_committed(file,0,size,1024*1024-4096,8192));
    assert(!horizon_memfile_committed_range(file,0,size,1024*1024-4096,&range,&committed) && committed && range==8192);
    assert(!horizon_memfile_alias(file,v1,0,size,0));horizon_memfile_use(file,0,size,-1);
    assert(anchors && v2[offset]==0x41);
    assert(!horizon_memfile_alias(file,v2,0,size,0));horizon_memfile_use(file,0,size,-1);
    assert(!anchors);
    assert(horizon_memfile_pread(file,(char*)readback,sizeof(readback),offset)==sizeof(readback));
    assert(readback[0]==0x41);
    /* Partial anchor and alias failures leave no leaked pages or anchors. */
    anchor_calls=0;fail_anchor=4;
    assert(horizon_memfile_map(file,v1,0,size)==-1 && !anchors);fail_anchor=0;
    alias_calls=0;fail_alias=4;
    assert(horizon_memfile_map(file,v1,0,size)==-1 && !anchors);fail_alias=0;
    assert(!horizon_memfile_map(file,v1,0,size));
    assert(!horizon_memfile_alias(file,v1,0,size,0));
    unanchor_calls=0;fail_unanchor=1;horizon_memfile_use(file,0,size,-1);
    assert(anchors);fail_unanchor=0;horizon_memfile_use(file,0,size,-1);assert(!anchors);
    horizon_memfile_unref(file);assert(!live_allocs);
    munmap(v1,size);munmap(v2,size);
    puts("PASS 16-MiB section: shared aliases, cross-piece descriptor I/O, SEC_RESERVE bookkeeping, anchor/alias failure cleanup");
#endif
}
int main(void) {
#ifndef TEST_BASELINE
    test_backing();
#endif
    test_memfile();
    assert(!live_allocs && !anchors);
    return 0;
}
