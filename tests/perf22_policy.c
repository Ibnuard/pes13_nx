/* Include the production pinned Box64 environment and existing policy checks. */
#define main perf17_policy_main
#define wine_nx_runtime_trace perf17_test_trace
#include "perf17_policy.c"
#undef main
#undef wine_nx_runtime_trace
void wine_nx_runtime_trace(const char *) __attribute__((weak));
#include "../src/runtime/pes13_perf19.h"
#include "../src/runtime/pes13_perf20.h"
#include "../src/runtime/pes13_perf21.h"
#include "../src/runtime/pes13_perf22.h"
void wine_nx_runtime_trace(const char *text) { perf17_test_trace(text); }

int main(int argc, char **argv)
{
    assert(argc==5); assert(!perf17_policy_main(2,argv));
    memset(&box64env,0,sizeof(box64env));
    box64env.dynarec_safeflags=2; box64env.dynarec_strongmem=1;
    box64env.dynarec_x87double=1; box64env.dynarec_wait=1; box64env.dynarec_div0=1;
    box64env_t original=box64env;
    pes21_mode=1; pes22_mode=1; pes17_identity=-1;
    wine_nx_vk_successful_presents=1;
    assert(pes22_select(0x113120c)==&box64env && !pes22_active);
    pes17_identity=1; wine_nx_vk_successful_presents=0;
    assert(pes22_select(0x113120c)==&box64env && !pes22_active);
    wine_nx_vk_successful_presents=1;
    const uintptr_t excluded[]={0,0x400000,0x400fff,0x13d1000,0x13d2000,0x1c61000,
        0x1c99b20,0xfa390000,0xffcb0000,0x112f000,0x112fb90,0x112ffff,UINTPTR_MAX};
    for (size_t i=0;i<sizeof(excluded)/sizeof(*excluded);++i)
        assert(pes22_select(excluded[i])==&box64env);
    assert(!pes22_active);
    pes22_mode=0;
    box64env_t *control=pes22_select(0x113120c);
    assert(control==&pes21_env && !pes22_active);
    assert(control->dynarec_fastround==1 && control->dynarec_x87double==1);
    box64env_t expected=*control, old_control=*control;
    expected.dynarec_x87double=0; expected.is_dynarec_x87double_overridden=1;
    expected.is_any_overridden=1; pes22_mode=1;
    const uintptr_t selected[]={0x401000,0x923070,0x93b85f,0x112efff,0x1130000,0x113120c,0x13d0fff};
    for (size_t i=0;i<sizeof(selected)/sizeof(*selected);++i) {
        box64env_t *env=pes22_select(selected[i]);
        assert(env==&pes22_env && !memcmp(env,&expected,sizeof(expected)));
        struct { box64env_t *env; } fixture={env}, *dyn=&fixture;
        assert(BOX64DRENV(dynarec_x87double)==0 && BOX64ENV(dynarec_x87double)==1);
        assert(BOX64DRENV(dynarec_fastround)==1 && BOX64ENV(dynarec_fastround)==0);
        assert(BOX64DRENV(dynarec_safeflags)==2 && BOX64DRENV(dynarec_strongmem)==1);
        assert(BOX64DRENV(dynarec_fastnan)==0 && BOX64DRENV(dynarec_callret)==0);
    }
    assert(!memcmp(&box64env,&original,sizeof(original)));
    assert(!memcmp(&pes21_env,&old_control,sizeof(old_control)));
    assert(wine_nx_perf22_block_end(0x112eff0,UINTPTR_MAX,&pes22_env)==0x112efff);
    assert(wine_nx_perf22_block_end(0x1130000,UINTPTR_MAX,&pes22_env)==0x13d0fff);
    assert(wine_nx_perf22_block_end(0x1130000,0x1131234,&pes22_env)==0x1131234);
    assert(wine_nx_perf22_block_end(0x112fb90,UINTPTR_MAX,&box64env)==UINTPTR_MAX);
    assert(wine_nx_perf22_block_end(0x1130000,UINTPTR_MAX,&pes21_env)==0x13d0fff);
    dynablock_t db={0}; pes17_capture=0;
    wine_nx_perf22_completed(&db,&box64env); assert(!pes22_completed && !pes21_completed);
    wine_nx_perf22_completed(&db,&pes22_env); assert(pes22_completed==1 && pes21_completed==1);
    wine_nx_perf22_completed(&db,&pes21_env); assert(pes22_completed==1 && pes21_completed==2);
    pes22_mode=0;
    assert(pes22_select(0x113120c)==&pes21_env);
    pes21_mode=0; pes22_mode=1;
    assert(pes22_select(0x113120c)==&box64env);
    wine_nx_perf22_report();
    puts("PERF22 identity/present/scope gates, matrix/DLL exclusions, SAFEFLAGS=2, only X87DOUBLE differs from PERF21, immutable baseline, completion and bounds PASS");
    return 0;
}
