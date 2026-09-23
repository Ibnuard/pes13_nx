#include <assert.h>
#include <stdlib.h>
#include "../src/runtime/pes13_perf37_probe.h"
struct nx_arena { uint8_t *rw,*rx; size_t used; };
typedef struct { void *block,*x64_addr; size_t native_size,x64_size; int done; } dynablock_t;
static uint8_t backing[256];
static struct nx_arena arena={backing,(uint8_t *)(uintptr_t)0x10000000,sizeof(backing)};
static dynablock_t block;
static int exists=1;
static struct nx_arena *find_arena(const void *p,size_t *offset) {
    uintptr_t pc=(uintptr_t)p;
    if(pc<(uintptr_t)arena.rx || pc-(uintptr_t)arena.rx>=sizeof(backing)) return NULL;
    *offset=pc-(uintptr_t)arena.rx; return &arena;
}
static dynablock_t *block_at(struct nx_arena *a,size_t offset) {
    (void)a;(void)offset; return exists ? &block : NULL;
}
static uintptr_t getX64Address(dynablock_t *db,uintptr_t pc) {
    assert(pc>=(uintptr_t)db->block && pc-(uintptr_t)db->block<db->native_size);
    return (uintptr_t)db->x64_addr+(pc-(uintptr_t)db->block)/4;
}
#include "../src/runtime/pes13_perf37_sample.h"
static unsigned rows,word_rows,block_rows;
static void output(const char *s) {
    assert(strlen(s)<600);
    ++rows;
    if(strstr(s,"[JIT37-WORDS]")) ++word_rows;
    if(strstr(s,"[JIT37-BLOCK]")) ++block_rows;
}
int main(void) {
    struct pes37_sample s; struct pes37_hist h={0};
    block=(dynablock_t){arena.rx+32,(void *)(uintptr_t)0x112fb90,128,100,1};
    uint32_t word=0x1e622820; memcpy(backing+36,&word,4);
    assert(wine_nx_box64_sample_detail((uintptr_t)arena.rx+36,&s));
    assert(s.valid && s.word==word && s.guest_pc==0x112fb91 && s.block==0x112fb90);
    struct pes37_sample saved=s;
    assert(!wine_nx_box64_sample_detail(0,&s) && !s.valid);
    assert(!wine_nx_box64_sample_detail((uintptr_t)arena.rx+37,&s));
    assert(!wine_nx_box64_sample_detail((uintptr_t)arena.rx+28,&s));
    assert(!wine_nx_box64_sample_detail((uintptr_t)arena.rx+160,&s));
    block.done=0; assert(!wine_nx_box64_sample_detail((uintptr_t)arena.rx+36,&s)); block.done=1;
    exists=0; assert(!wine_nx_box64_sample_detail((uintptr_t)arena.rx+36,&s)); exists=1;
    arena.used=38; assert(!wine_nx_box64_sample_detail((uintptr_t)arena.rx+36,&s));
    arena.used=32; assert(!wine_nx_box64_sample_detail((uintptr_t)arena.rx+36,&s));
    arena.used=sizeof(backing);
    block.native_size=7; assert(!wine_nx_box64_sample_detail((uintptr_t)arena.rx+36,&s));
    block.native_size=128;
    /* Rejected samples cannot enter the histogram. */
    pes37_add(&h,&s); assert(h.samples==0);
    for(unsigned i=0;i<200;++i) {
        s=saved; s.word=i; s.block=0x400000+32*i; pes37_add(&h,&s);
    }
    assert(h.samples==200 && h.words_used==128 && h.blocks_used==128);
    assert(h.words_dropped==72 && h.blocks_dropped==72);
    s=saved; s.word=0; s.block=0x400000;
    for(unsigned i=0;i<10000;++i) pes37_add(&h,&s);
    assert(h.words[0].count==10001 && h.blocks[0].count==10001);
    assert(h.words_dropped==72 && h.blocks_dropped==72);
    pes37_report(176,'w',&h,output);
    assert(rows==24 && word_rows==11 && block_rows==12);
    memset(&h,0,sizeof(h)); rows=0; pes37_report(176,'w',&h,output); assert(!rows);
    puts("PERF37: invalid/padding/unfinished sample rejection; bounded saturation; retained counts; output bounds PASS");
}
