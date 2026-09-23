#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../src/runtime/pes13_perf20_fuse.h"

struct pes20_result perf20_test_fuse(uint32_t *c, size_t bytes) { return pes20_fuse(c, bytes); }
int perf20_test_gap(uint32_t w) { return pes20_gap(w); }

#ifndef PERF20_SHARED
static const uint32_t guard[] = {
    0xb9431c01, 0x330a2c21, 0x53010425, 0x331f0025,
    0xd53b4401, 0xaa0103e4, 0xb36a04a1, 0xd51b4401,
    0x1e690908, 0xd51b4404, /* FMUL d8,d8,d9; restore */
};

int main(void)
{
    uint32_t code[128], old[128];
    struct pes20_result r;
    size_t i, bit;
    memcpy(code, guard, sizeof(guard)); memcpy(code+10, guard, sizeof(guard));
    code[20] = 0xd61f0040;
    memcpy(old, code, 21*4);
    r = pes20_fuse(code, 21*4);
    assert(r.guards == 2 && r.merged == 1 && r.runs == 1 && !r.flow_rejected);
    assert(code[9] == 0x14000009 && code[10] == 0x14000008);
    /* Short input and excessive size must never be read. */
    assert(!pes20_fuse(NULL, 0).merged && !pes20_fuse(NULL, 65540).merged);
    assert(!pes20_fuse(NULL, 3).merged);
    for (i=1; i<40; ++i) {
        memcpy(code, old, 21*4);
        assert(!pes20_fuse(code, i).merged);
    }
    /* A mutated template cannot silently become a loose pattern match. */
    for (i=0; i<8; ++i) for (bit=0; bit<32; ++bit) {
        memcpy(code, old, 21*4); code[i] ^= UINT32_C(1)<<bit;
        assert(!pes20_fuse(code, 21*4).merged);
    }
    const uint32_t branches[] = {0x14000000,0x94000000,0x54ffffe0,0x34ffffe0,
        0xb5ffffe0,0x36000000,0xb7000000,0xd61f0020,0xd63f0020,0xd65f03c0};
    for (i=0; i<sizeof(branches)/sizeof(*branches); ++i) {
        memcpy(code, old, 21*4); code[20]=branches[i];
        uint32_t saved=code[20]; r=pes20_fuse(code,21*4);
        assert(r.flow_rejected && !r.merged);
        assert(!memcmp(code,old,20*4) && code[20]==saved);
    }
    const uint32_t barriers[] = {
        0x1e624000, /* unguarded narrowing depends on the original host mode */
        0x1e602800, /* unguarded FP arithmetic */
        0xb9031c01, /* emulator-state store */
        0xb9400144, /* guest load clobbers saved FPCR in x4 */
        0x2a0403ea, /* guest move reads saved FPCR */
        0xd5033bbf, /* unknown barrier */
        0xd51b4401, /* extra FPCR update */
        0xd53b4401, /* extra FPCR read */
    };
    for (i=0; i<sizeof(barriers)/sizeof(*barriers); ++i) {
        memcpy(code,guard,sizeof(guard)); code[10]=barriers[i];
        memcpy(code+11,guard,sizeof(guard)); code[21]=0xd61f0040;
        memcpy(old,code,22*4); r=pes20_fuse(code,22*4);
        assert(r.guards==2 && !r.merged && !memcmp(code,old,22*4));
    }
    /* 32 whitelisted gap words is accepted; 33 terminates the run. */
    for (i=32; i<=33; ++i) {
        memcpy(code,guard,sizeof(guard));
        for (size_t j=0;j<i;++j) code[10+j]=0xd503201f;
        memcpy(code+10+i,guard,sizeof(guard)); code[20+i]=0xd61f0040;
        r=pes20_fuse(code,(21+i)*4); assert(r.merged==(i==32));
    }
    puts("PERF20 fusion bounds, exact templates, barriers and all-or-none control-flow rejection PASS");
    return 0;
}
#endif
