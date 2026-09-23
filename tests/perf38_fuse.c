#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../src/runtime/pes13_perf38_fuse.h"
struct pes20_result perf38_test_fuse(uint32_t *c, size_t n) { return pes38_fuse(c,n); }
struct pes20_result perf38_test_old(uint32_t *c, size_t n) { return pes20_fuse(c,n); }
int perf38_test_target(uint32_t w, size_t i, int64_t *out) { return pes38_target(w,i,out); }
int perf38_test_gap(uint32_t w) { return pes20_gap(w); }
#ifndef PERF38_SHARED
static const uint32_t guard[] = {
    0xb9431c01,0x330a2c21,0x53010425,0x331f0025,0xd53b4401,
    0xaa0103e4,0xb36a04a1,0xd51b4401,0x1e690908,0xd51b4404
};
int main(void)
{
    uint32_t c[96], saved[96]; size_t i; struct pes20_result r;
    assert(!pes38_fuse(NULL,0).merged && !pes38_fuse(NULL,3).merged && !pes38_fuse(NULL,65540).merged);
    for (i=0;i<3;++i) memcpy(c+i*10,guard,sizeof guard);
    c[30]=0x54fffc40; /* B.eq to word 0: first guard is a region entry. */
    c[31]=0xd61f0040;
    r=pes38_fuse(c,128); assert(r.guards==3 && r.merged==1 && !r.flow_rejected);
    /* Branch targets inside either guard or intervening gap must prevent
     * fusion. Test all words, both forward and backward edges. */
    for (i=0;i<23;++i) {
        c[0]=0x54000000 | ((uint32_t)(i+1)<<5);
        memcpy(c+1,guard,sizeof guard); c[11]=0xd503201f;
        memcpy(c+12,guard,sizeof guard); c[22]=0xd61f0040;
        if (i<21) { r=pes38_fuse(c,92); assert(!r.merged); }
    }
    /* An unrelated conditional branch no longer discards a safe run. */
    memcpy(c,guard,sizeof guard); memcpy(c+10,guard,sizeof guard);
    c[20]=0x54000040; c[21]=0xd503201f; c[22]=0xd61f0040;
    memcpy(saved,c,92); assert(pes20_fuse(saved,92).flow_rejected);
    r=pes38_fuse(c,92); assert(r.merged==1 && !r.flow_rejected);
    /* Calls, RET, and arbitrary register branches are rejected atomically. */
    const uint32_t unsafe[]={0x94000000,0xd63f0020,0xd65f03c0,0xd61f0060,0x54000010};
    for (i=0;i<sizeof unsafe/sizeof *unsafe;++i) {
        memcpy(c,guard,sizeof guard); memcpy(c+10,guard,sizeof guard); c[20]=unsafe[i];
        memcpy(saved,c,84); r=pes38_fuse(c,84);
        assert(r.flow_rejected && !r.merged && !memcmp(c,saved,84));
    }
    puts("PERF38 bounds, direct branch entries, unsupported flow and atomic rejection PASS");
    return 0;
}
#endif
