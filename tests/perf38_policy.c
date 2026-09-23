#define main perf17_policy_main
#define wine_nx_runtime_trace perf17_test_trace
#include "perf17_policy.c"
#undef main
#undef wine_nx_runtime_trace
void wine_nx_runtime_trace(const char *) __attribute__((weak));
#include "../local/perf38/pes13_perf20_capture.h"
void wine_nx_runtime_trace(const char *text) { perf17_test_trace(text); }
int main(void)
{
    const uint32_t guard[]={0xb9431c01,0x330a2c21,0x53010425,0x331f0025,
        0xd53b4401,0xaa0103e4,0xb36a04a1,0xd51b4401,0x1e690908,0xd51b4404};
    uint32_t code[23], original[23]; dynablock_t db={0};
    memcpy(original,guard,40);memcpy(original+10,guard,40);
    original[20]=0x54000040;original[21]=0xd503201f;original[22]=0xd61f0040;
    memcpy(code,original,sizeof code);
    db.block=code;db.native_size=sizeof code;db.x64_size=120;db.is32bits=1;
    db.x64_addr=(void *)0x113027b;pes38_mode=1;pes20_mode=1;pes17_identity=-1;
    wine_nx_perf20_patch(&db);assert(!pes38_seen);
    pes17_identity=1;pes20_mode=0;wine_nx_perf20_patch(&db);assert(!pes38_seen);
    pes20_mode=1;db.is32bits=0;wine_nx_perf20_patch(&db);assert(!pes38_seen);db.is32bits=1;
    db.sep_size=1;wine_nx_perf20_patch(&db);assert(!pes38_seen);db.sep_size=0;
    db.callret_size=1;wine_nx_perf20_patch(&db);assert(!pes38_seen);db.callret_size=0;
    db.x64_addr=(void *)0x112fb90;wine_nx_perf20_patch(&db);assert(!pes38_seen);
    db.x64_addr=(void *)0x93df30;wine_nx_perf20_patch(&db);assert(!pes38_seen);
    db.x64_addr=(void *)0x1130fff;wine_nx_perf20_patch(&db);assert(!pes38_seen);
    db.x64_addr=(void *)0x113027b;pes38_mode=0;wine_nx_perf20_patch(&db);
    assert(!pes38_seen && !memcmp(code,original,sizeof code));
    pes38_mode=1;wine_nx_perf20_patch(&db);
    assert(pes38_seen==1 && pes38_merged==1 && pes38_hot_merged[0]==1);
    assert(code[9]==0x14000009 && code[10]==0x14000008);
    wine_nx_perf38_report();wine_nx_perf20_report();
    puts("PERF38 generated wrapper identity, matrix exclusion, scope, secondary-entry and rollback PASS");
    return 0;
}
