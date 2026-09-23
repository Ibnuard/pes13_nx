/* Exercise the actual environment headers with the pinned Box64 structures. */
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
#include <sys/mman.h>
#include "../local/perf32/pes13_perf25_env.h"
#include "../src/runtime/pes13_perf32.h"
void wine_nx_runtime_trace(const char *line) { perf17_test_trace(line); }
int main(int argc,char **argv)
{
    assert(!perf17_policy_main(argc,argv));
    pes21_active=0;pes21_mode=1;pes22_mode=0;pes32_mode=1;
    wine_nx_vk_successful_presents=0;
    box64env_t original=box64env;
    assert(pes32_select(0x93df30,pes22_select(0x93df30))==&box64env && !pes32_ready);
    wine_nx_vk_successful_presents=1;
    box64env_t *base=pes22_select(0x93df30), baseline=*base;
    assert(base==&pes21_env && base->dynarec_callret==0);
    pes32_mode=0;assert(pes32_select(0x93df30,base)==base);pes32_mode=1;
    pes17_identity=-1;assert(pes32_select(0x93df30,base)==base);pes17_identity=1;
    box64env_t other=baseline;assert(pes32_select(0x93df30,&other)==&other);
    const uintptr_t excluded[]={0,0x400fff,0x112f000,0x112fb90,0x112ffff,
        0x1150000,0x115c36f,0x116ffff,0x13d1000,0xfa390000,UINTPTR_MAX};
    for(unsigned i=0;i<sizeof(excluded)/sizeof(*excluded);++i)
        assert(pes32_select(excluded[i],base)==base);
    box64env_t expected=baseline;
    expected.dynarec_bigblock=3;expected.is_dynarec_bigblock_overridden=1;expected.is_any_overridden=1;
    const uintptr_t ranges[][2]={{0x401000,0x112f000},{0x1130000,0x1150000},{0x1170000,0x13d1000}};
    for(unsigned r=0;r<3;++r) for(unsigned pass=0;pass<4;++pass) {
        uintptr_t lo=ranges[r][0],hi=ranges[r][1];
        box64env_t *env=pes32_select(lo,base);
        assert(env==&pes32_env && !memcmp(env,&expected,sizeof(expected)));
        assert(pes32_select(hi-1,base)==env && pes32_select(hi,base)==base);
        assert(wine_nx_perf32_block_end(lo,UINTPTR_MAX,env)==hi-1);
        assert(wine_nx_perf32_block_end(lo,lo+32,env)==lo+32);
        assert(wine_nx_perf32_base(env)==base);
    }
    assert(!memcmp(base,&baseline,sizeof(baseline)) && !memcmp(&box64env,&original,sizeof(original)));
    assert(wine_nx_perf32_block_end(0x920000,UINTPTR_MAX,base)==0x112efff);
    assert(wine_nx_perf32_block_end(0x920000,UINTPTR_MAX,&box64env)==UINTPTR_MAX);
    pes22_mode=1;assert(pes32_select(0x93df30,pes22_select(0x93df30))==&pes22_env);pes22_mode=0;
    void *mapped=mmap((void*)0x93d000,4096,PROT_READ|PROT_WRITE,
        MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
    assert(mapped==(void*)0x93d000);unsigned char *code=(void*)0x93df30;
    memcpy(code,pes25_copy_guest,sizeof(pes25_copy_guest));pes25_mode=1;
    /* Previously chosen environments remain immutable even if presents change. */
    wine_nx_vk_successful_presents=0;
    for(unsigned pass=0;pass<4;++pass) assert(wine_nx_perf25_copy(0x93df43,&pes32_env));
    assert(!wine_nx_perf25_copy(0x93df43,&box64env));
    code[20]^=1;assert(!wine_nx_perf25_copy(0x93df43,&pes32_env));code[20]^=1;
    pes25_mode=0;assert(!wine_nx_perf25_copy(0x93df43,&pes32_env));pes25_mode=1;
    pes17_capture=0;dynablock_t db={0};db.x64_addr=(void*)0x93df30;db.x64_size=35;db.native_size=224;
    unsigned previous=pes21_completed;
    wine_nx_perf32_completed(&db,&pes32_env);
    assert(pes32_completed_count==1 && pes21_completed==previous+1);
    assert(pes32_guest_bytes==35 && pes32_native_bytes==224 && pes32_max_guest==35 && pes32_max_native==224);
    wine_nx_perf32_completed(&db,&box64env);assert(pes32_completed_count==1);
    /* The startup capture is retained through the wrapper, before any present. */
    unsigned char guest[42]={0},native[64]={0};memset(pes17_snapshots,0,sizeof(pes17_snapshots));
    pes17_capture=1;db.x64_addr=(void*)0x115c356;db.x64_readaddr=(uintptr_t)guest;
    db.x64_size=sizeof(guest);db.native_size=sizeof(native);db.block=native;db.is32bits=1;
    wine_nx_perf32_completed(&db,&box64env);assert(pes17_snapshots[5].state==2);
    munmap(mapped,4096);wine_nx_perf32_report();
    puts("PERF32 bounds, exclusions, four-pass immutability, only BIGBLOCK changed, copy/capture delegation PASS");
    return 0;
}
