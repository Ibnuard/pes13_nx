/* Real shared mappings; deliberate address fragmentation separate from RAM. */
#define main backing_fixture_main
#include "fextendo_page_store.c"
#undef main

static void release_view(struct horizon_memfile *f, void *view, size_t offset, size_t size) {
    assert(!horizon_memfile_alias(f,view,offset,size,0));
    horizon_memfile_use(f,offset,size,-1);
}
static void clean(void) { assert(!anchors && !live_allocs); }
static void reset_faults(void) {
    anchor_calls=alias_calls=unanchor_calls=undo_calls=0;
    fail_anchor=fail_alias=fail_unanchor=fail_undo=0;
    anchor_address_budget=-1;
}

int main(void) {
    const size_t size=0x4580000; /* The two failed requests in the supplied log. */
    limit=2*size;anchor_address_limit=32*1024*1024;
    struct horizon_memfile *f=horizon_memfile_alloc(size,0,&ops);
    assert(f && f->pages.data && !f->pages.pieces); /* Physical allocation works. */
    unsigned char *a=reserve(size),*b=reserve(size);
#ifdef TEST_ANCHOR_BASELINE
    assert(horizon_memfile_map(f,a,0,size)==-1 && errno==EADDRNOTAVAIL);
    assert(!anchors);horizon_memfile_unref(f);munmap(a,size);munmap(b,size);clean();
    puts("PASS baseline: 69.5-MiB backing exists but one contiguous anchor cannot fit");
    return 0;
#else
    assert(!horizon_memfile_map(f,a,0,size));
    unsigned pieces=0;
    for(struct anchor_token *t=anchors;t;t=t->next) {
        assert(t->size<=anchor_address_limit);++pieces;
    }
    assert(pieces>1 && pieces<16);
    assert(!horizon_memfile_map(f,b,0,size));
    for(size_t i=0;i<size;i+=4096) {
        assert(a[i]==0 && b[i]==0);a[i]=(unsigned char)(i/4096);assert(b[i]==a[i]);
    }
    /* Descriptor access crosses a newly split anchor boundary. */
    const size_t boundary=f->anchors->count*4096;
    unsigned char data[96],out[96];memset(data,0x6d,sizeof(data));
    assert(horizon_memfile_pwrite(f,(char*)data,sizeof(data),boundary-32)==sizeof(data));
    assert(!memcmp(a+boundary-32,data,sizeof(data)) && !memcmp(b+boundary-32,data,sizeof(data)));
    b[boundary]=0x42;
    assert(horizon_memfile_pread(f,(char*)out,sizeof(out),boundary-32)==sizeof(out));
    assert(out[32]==0x42);
    /* A second section like the second failed request; it shares no backing. */
    struct horizon_memfile *second=horizon_memfile_alloc(size,0,&ops);
    void *other=reserve(size);assert(second && !horizon_memfile_map(second,other,0,size));
    ((unsigned char*)other)[boundary]=0x77;assert(a[boundary]==0x42);
    release_view(second,other,0,size);horizon_memfile_unref(second);munmap(other,size);
    /* Partial view stays live after both full views have gone. */
    size_t offset=8*1024*1024,length=40*1024*1024;
    unsigned char *partial=reserve(length);
    assert(!horizon_memfile_map(f,partial,offset,length));
    release_view(f,a,0,size);release_view(f,b,0,size);
    assert(anchors && partial[boundary-offset]==0x42);
    partial[boundary-offset]=0x93;
    release_view(f,partial,offset,length);assert(!anchors);
    assert(horizon_memfile_pread(f,(char*)out,1,boundary)==1 && out[0]==0x93);
    munmap(partial,length);
    /* Exhaustion after partial progress must trim every newly made anchor. */
    reset_faults();anchor_address_budget=2;
    assert(horizon_memfile_map(f,a,0,size)==-1 && errno==ENOMEM && !anchors);
    assert(anchor_calls<64);
    reset_faults();anchor_address_budget=0;
    assert(horizon_memfile_map(f,a,0,size)==-1 && errno==ENOMEM && !anchors);
    assert(anchor_calls<32);
    /* ENOMEM from metadata/kernel is terminal, not a retryable VA miss. */
    reset_faults();fail_anchor=2;
    assert(horizon_memfile_map(f,a,0,size)==-1 && errno==ENOMEM && anchor_calls==2 && !anchors);
    reset_faults();fail_alias=2;
    assert(horizon_memfile_map(f,a,0,size)==-1 && errno==EIO && !anchors);
    reset_faults();
    assert(!horizon_memfile_map(f,a,0,size));
    assert(a[boundary]==0x93);release_view(f,a,0,size);
    horizon_memfile_unref(f);munmap(a,size);munmap(b,size);clean();
    /* Non-power-of-two tails down to one page; repeat to check lifecycle. */
    for(unsigned pass=0;pass<10;++pass) {
        anchor_address_limit=4096;
        f=horizon_memfile_alloc(9*4096,0,&ops);a=reserve(9*4096);assert(f);
        assert(!horizon_memfile_map(f,a,0,9*4096));
        for(unsigned page=0;page<9;++page)a[page*4096]=(unsigned char)pass;
        release_view(f,a,0,9*4096);horizon_memfile_unref(f);munmap(a,9*4096);clean();
    }
    puts("PASS two 69.5-MiB sections: fragmented anchors, shared/partial views and cross-boundary I/O");
    puts("PASS exhaustion rollback, terminal errors, successful retry, page-sized tails and repeated cleanup");
    return 0;
#endif
}
