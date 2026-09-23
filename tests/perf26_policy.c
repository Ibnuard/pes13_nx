#define main perf17_policy_main
#define wine_nx_runtime_trace perf17_test_trace
#include "perf17_policy.c"
#undef main
#undef wine_nx_runtime_trace
void wine_nx_runtime_trace(const char *) __attribute__((weak));
#include "../src/runtime/pes13_perf19.h"
#include "../src/runtime/pes13_perf20.h"
#include "../src/runtime/pes13_perf26.h"
#include "../local/perf26/pes13_perf21_callret.h"
#include "../src/runtime/pes13_perf22.h"
void wine_nx_runtime_trace(const char *line) { perf17_test_trace(line); }
int main(int argc,char **argv)
{
    assert(!perf17_policy_main(argc,argv));
    memset(&box64env,0,sizeof(box64env));
    box64env.dynarec_safeflags=2;box64env.dynarec_strongmem=1;
    box64env.dynarec_x87double=1;box64env.dynarec_wait=1;box64env.dynarec_div0=1;
    box64env_t original=box64env;
    pes17_identity=1;pes21_mode=1;pes22_mode=0;pes26_mode=1;
    wine_nx_vk_successful_presents=0;
    const box64env_t *boot=pes22_select(0x93b85f);
    assert(boot==&box64env && !pes21_active);
    wine_nx_vk_successful_presents=1;
    assert(boot->dynarec_callret==0); /* earlier four-pass selection stays stable */
    const uintptr_t excluded[]={0,0x400fff,0x13d1000,0x112f000,0x112fb90,0x112ffff,0xfa390000,0xffcb0000,UINTPTR_MAX};
    for(unsigned i=0;i<sizeof(excluded)/sizeof(*excluded);++i) assert(pes22_select(excluded[i])==&box64env);
    pes17_identity=-1;assert(pes22_select(0x93b85f)==&box64env);pes17_identity=1;
    box64env_t expected=original;
    expected.dynarec_fastround=1;expected.is_dynarec_fastround_overridden=1;
    expected.dynarec_callret=2;expected.is_dynarec_callret_overridden=1;expected.is_any_overridden=1;
    for(unsigned pass=0;pass<4;++pass) {
        const box64env_t *env=pes22_select(0x93b85f);
        assert(env==&pes21_env && !memcmp(env,&expected,sizeof(expected)));
    }
    assert(!memcmp(&box64env,&original,sizeof(original)));
    assert(wine_nx_perf22_block_end(0x112eff0,UINTPTR_MAX,&pes21_env)==0x112efff);
    assert(wine_nx_perf22_block_end(0x1130000,UINTPTR_MAX,&pes21_env)==0x13d0fff);
    /* Control is read at launch; a subsequent launch constructs a fresh env. */
    pes21_active=0;pes26_mode=0;expected.dynarec_callret=0;expected.is_dynarec_callret_overridden=0;
    assert(!memcmp(pes22_select(0x9379f0),&expected,sizeof(expected)));
    wine_nx_perf26_report();
    puts("PERF26 scope, boot/DLL/matrix exclusion, immutable four-pass selection, control, SAFEFLAGS/math unchanged PASS");
    return 0;
}
