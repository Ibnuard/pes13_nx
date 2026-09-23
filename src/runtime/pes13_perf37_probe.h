/* Bounded sample data. Only the profiling thread writes it, under its existing
 * mutex. No hooks, counters or extra instructions in executed guest blocks. */
#ifndef PES13_PERF37_PROBE_H
#define PES13_PERF37_PROBE_H
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define PES37_SLOTS 128
struct pes37_sample {
    uintptr_t guest_pc, block;
    uint32_t word, guest_bytes, arm_bytes;
    int valid;
};
struct pes37_word { uint32_t word, count; };
struct pes37_block { uintptr_t address; uint32_t guest_bytes, arm_bytes, count; };
struct pes37_hist {
    uint32_t samples, words_used, blocks_used, words_dropped, blocks_dropped;
    struct pes37_word words[PES37_SLOTS];
    struct pes37_block blocks[PES37_SLOTS];
};
static inline void pes37_add(struct pes37_hist *h, const struct pes37_sample *s)
{
    unsigned i;
    if (!s->valid) return;
    ++h->samples;
    for (i=0;i<h->words_used;++i) if (h->words[i].word==s->word) break;
    if (i<PES37_SLOTS) {
        if (i==h->words_used) { h->words[i].word=s->word; ++h->words_used; }
        ++h->words[i].count;
    } else ++h->words_dropped;
    for (i=0;i<h->blocks_used;++i)
        if (h->blocks[i].address==s->block && h->blocks[i].guest_bytes==s->guest_bytes &&
            h->blocks[i].arm_bytes==s->arm_bytes) break;
    if (i<PES37_SLOTS) {
        if (i==h->blocks_used) {
            h->blocks[i]=(struct pes37_block){s->block,s->guest_bytes,s->arm_bytes,0};
            ++h->blocks_used;
        }
        ++h->blocks[i].count;
    } else ++h->blocks_dropped;
}

/* Called after all sampled threads have resumed. Rows fit the existing log
 * buffer. Every retained opcode count is reported; block detail is top 12. */
static inline void pes37_report(unsigned tid, char kind, const struct pes37_hist *h,
                                void (*output)(const char *))
{
    char line[600]; unsigned i,j,top[12],shown=0; int len;
    if (!h->samples) return;
    snprintf(line,sizeof(line),"[JIT37] %u%c samples=%u word_dropped=%u block_dropped=%u; wall samples, not CPU cycles",
             tid,kind,h->samples,h->words_dropped,h->blocks_dropped);
    output(line);
    for (i=0;i<h->words_used;) {
        len=snprintf(line,sizeof(line),"[JIT37-WORDS] %u%c",tid,kind);
        for (j=0;j<12 && i<h->words_used;++j,++i)
            len+=snprintf(line+len,sizeof(line)-(size_t)len," %08x:%u",h->words[i].word,h->words[i].count);
        output(line);
    }
    for (i=0;i<h->blocks_used;++i) {
        j=shown<12 ? shown++ : 12;
        for (;j>0 && h->blocks[top[j-1]].count<h->blocks[i].count;--j)
            if (j<12) top[j]=top[j-1];
        if (j<12) top[j]=i;
    }
    for (i=0;i<shown;++i) {
        const struct pes37_block *b=&h->blocks[top[i]];
        snprintf(line,sizeof(line),"[JIT37-BLOCK] %u%c guest=%lx guest_bytes=%u arm_bytes=%u samples=%u",
                 tid,kind,(unsigned long)b->address,b->guest_bytes,b->arm_bytes,b->count);
        output(line);
    }
}
#endif
