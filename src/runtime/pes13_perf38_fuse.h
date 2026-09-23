/* Size-preserving FPCR guard fusion within direct-control-flow regions.
 * Caller must exclude secondary-entry/CALLRET blocks and literal tables.
 * No arithmetic, rounding mode, guest address or native offset changes.
 * Only the pinned BR x2 dispatcher is accepted as an indirect exit. Calls
 * and other indirect transfers reject the entire block before mutation. */
#ifndef PES13_PERF38_FUSE_H
#define PES13_PERF38_FUSE_H
#include "pes13_perf20_fuse.h"

static int64_t pes38_signed(uint32_t imm, unsigned int bits)
{
    return (int64_t)imm - ((imm & (UINT32_C(1) << (bits-1))) ? (INT64_C(1) << bits) : 0);
}

/* Return 1 for a decoded direct branch, -1 for an unsupported transfer. */
static int pes38_target(uint32_t w, size_t i, int64_t *target)
{
    if ((w & 0xfc000000) == 0x14000000) {
        *target = (int64_t)i + pes38_signed(w & 0x03ffffff, 26); return 1;
    }
    if ((w & 0xff000010) == 0x54000000 || (w & 0x7e000000) == 0x34000000) {
        *target = (int64_t)i + pes38_signed((w >> 5) & 0x7ffff, 19); return 1;
    }
    if ((w & 0x7e000000) == 0x36000000) {
        *target = (int64_t)i + pes38_signed((w >> 5) & 0x3fff, 14); return 1;
    }
    if (pes20_branch(w) && w != 0xd61f0040) return -1;
    return 0;
}

/* The x87 memory-operand emitter widens its loaded float immediately after
 * setting FPCR, before the arithmetic. Keep that operation in place. The
 * old ten-word recognizer missed this eleven-word form altogether. */
static unsigned int pes38_guard(const uint32_t *c, size_t left, size_t *length)
{
    uint32_t normalized[10]; unsigned int variant;
    *length=10;
    variant=pes20_guard(c,left);
    if (variant || left<11 || (c[8]&0xfffffc00)!=0x1e22c000) return variant;
    for (size_t j=0;j<8;++j) normalized[j]=c[j];
    normalized[8]=c[9]; normalized[9]=c[10];
    variant=pes20_guard(normalized,10);
    if (variant) *length=11;
    return variant;
}

static struct pes20_result pes38_fuse(uint32_t *c, size_t bytes)
{
    struct pes20_result r = {0};
    /* 2 KiB, stack-local: no allocation, shared state or execution hook. */
    unsigned char entries[2048] = {0};
    size_t n = bytes/4, i, j, last = 0;
    unsigned int variant = 0, run_length = 0, gap = 0;
    if (!bytes || bytes % 4 || bytes > 65536) return r;
    for (i = 0; i < n; ++i) {
        int64_t target = 0;
        int flow = pes38_target(c[i], i, &target);
        if (flow < 0) { r.flow_rejected = 1; return r; }
        if (flow && target >= 0 && target < (int64_t)n)
            entries[(size_t)target/8] |= (unsigned char)(1u << ((size_t)target%8));
    }
    for (i = 0; i < n;) {
        size_t length;
        unsigned int current = pes38_guard(c+i, n-i, &length), entered = 0;
        if (current) {
            /* An entry anywhere in the guard, including its arithmetic or
             * restore, makes it ineligible on both sides of a fused run. */
            for (j = i; j < i+length; ++j)
                entered |= entries[j/8] & (1u << (j%8));
            ++r.guards;
            if (!entered && variant == current && gap <= 32) {
                c[i] = 0x14000008;
                c[last] = last+1 == i ? 0x14000009 : 0xd503201f;
                ++r.merged;
                if (run_length == 1) ++r.runs;
                ++run_length;
            } else run_length = 1;
            variant = entered ? 0 : current;
            last = i+length-1; gap = 0; i += length;
        } else {
            if ((entries[i/8] & (1u << (i%8))) || !pes20_gap(c[i]) || ++gap > 32) {
                variant = 0; run_length = 0;
            }
            ++i;
        }
    }
    return r;
}
#endif
