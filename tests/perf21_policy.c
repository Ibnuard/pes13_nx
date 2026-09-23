#define main perf17_policy_main
#define wine_nx_runtime_trace perf17_test_trace
#include "perf17_policy.c"
#undef main
#undef wine_nx_runtime_trace
void wine_nx_runtime_trace(const char *) __attribute__((weak));
#include "../src/runtime/pes13_perf19.h"
#include "../src/runtime/pes13_perf20.h"
#include "../src/runtime/pes13_perf21.h"
void wine_nx_runtime_trace(const char *text) { perf17_test_trace(text); }

int main(int argc, char **argv)
{
    assert(argc==5); assert(!perf17_policy_main(2,argv));
    memset(&box64env,0,sizeof(box64env));
    box64env.dynarec_safeflags=2;
    box64env.dynarec_strongmem=1;
    box64env.dynarec_x87double=1;
    box64env.dynarec_wait=1;
    box64env.dynarec_div0=1;
    box64env_t original=box64env, expected=box64env;
    pes17_identity=1; pes21_mode=0; wine_nx_vk_successful_presents=1;
    assert(pes21_select(0x113120c)==&box64env && !pes21_active);
    pes21_mode=1; pes17_identity=-1;
    assert(pes21_select(0x113120c)==&box64env && !pes21_active);
    pes17_identity=1; wine_nx_vk_successful_presents=0;
    assert(pes21_select(0x113120c)==&box64env && !pes21_active);
    assert(pes21_boot_fallback==1);
    const uintptr_t excluded[]={0,0x400000,0x400fff,0x13d1000,0x13d2000,
        0x1c61000,0x1c99b20,0xfa390000,0xffcb0000,0x112f000,0x112fb90,0x112ffff,UINTPTR_MAX};
    wine_nx_vk_successful_presents=1;
    for (size_t i=0;i<sizeof(excluded)/sizeof(*excluded);++i)
        assert(pes21_select(excluded[i])==&box64env);
    expected.dynarec_fastround=1;
    expected.is_dynarec_fastround_overridden=1;
    expected.is_any_overridden=1;
    const uintptr_t selected[]={0x401000,0x923070,0x93b85f,0x112efff,0x1130000,0x113120c,0x13d0fff};
    for (size_t i=0;i<sizeof(selected)/sizeof(*selected);++i) {
        box64env_t *env=pes21_select(selected[i]);
        assert(env==&pes21_env && !memcmp(env,&expected,sizeof(expected)));
        struct { box64env_t *env; } fixture={env}, *dyn=&fixture;
        /* This is the real pinned Box64 macro used by generated emitters. */
        assert(BOX64DRENV(dynarec_fastround)==1 && BOX64ENV(dynarec_fastround)==0);
        assert(BOX64DRENV(dynarec_safeflags)==2 && BOX64ENV(dynarec_safeflags)==2);
        assert(BOX64DRENV(dynarec_fastnan)==0 && BOX64DRENV(dynarec_x87double)==1);
        assert(BOX64DRENV(dynarec_strongmem)==1 && BOX64DRENV(dynarec_callret)==0);
    }
    assert(!memcmp(&box64env,&original,sizeof(original)));
    assert(wine_nx_perf21_block_end(0x112eff0,UINTPTR_MAX,&pes21_env)==0x112efff);
    assert(wine_nx_perf21_block_end(0x1130000,UINTPTR_MAX,&pes21_env)==0x13d0fff);
    assert(wine_nx_perf21_block_end(0x1130000,0x1131234,&pes21_env)==0x1131234);
    assert(wine_nx_perf21_block_end(0x112fb90,UINTPTR_MAX,&pes21_env)==UINTPTR_MAX);
    assert(wine_nx_perf21_block_end(0x1130000,UINTPTR_MAX,&box64env)==UINTPTR_MAX);
    pes17_capture=0;
    dynablock_t db={0};
    wine_nx_perf21_completed(&db,&box64env); assert(!pes21_completed);
    wine_nx_perf21_completed(&db,&pes21_env); assert(pes21_completed==1);
    pes21_mode=0;
    assert(pes21_select(0x113120c)==&box64env);
    wine_nx_perf21_completed(&db,&box64env); assert(pes21_completed==1);
    /* Runtime mode is read once at init; disabling in this test exercises fallback. */
    wine_nx_perf21_report();
    puts("PERF21 first-present gate, DLL/matrix/packer exclusions, real emitter macro, SAFEFLAGS=2, only FASTROUND differs, no global mutation PASS");
    return 0;
}
