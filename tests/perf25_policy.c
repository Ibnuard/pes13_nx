/* Real environment selection and bounded capture; no guest execution here. */
#define main perf17_policy_main
#define wine_nx_runtime_trace perf17_test_trace
#include "perf17_policy.c"
#undef main
#undef wine_nx_runtime_trace
void wine_nx_runtime_trace(const char *) __attribute__((weak));
#include <sys/mman.h>
#include "../src/runtime/pes13_perf19.h"
#include "../src/runtime/pes13_perf20.h"
#include "../src/runtime/pes13_perf21.h"
#include "../src/runtime/pes13_perf22.h"
#include "../src/runtime/pes13_perf25.h"
void wine_nx_runtime_trace(const char *text) { perf17_test_trace(text); }
int main(int argc,char **argv)
{
    assert(!perf17_policy_main(argc,argv));
    void *mapped=mmap((void*)0x93d000,4096,PROT_READ|PROT_WRITE,
        MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
    assert(mapped==(void*)0x93d000);
    unsigned char *code=(void*)0x93df30;
    memcpy(code,pes25_copy_guest,sizeof(pes25_copy_guest));
    pes17_identity=1;pes25_mode=1;pes21_mode=1;pes22_mode=0;
    wine_nx_vk_successful_presents=0;
    const void *boot=pes22_select(0x93df43);
    assert(boot==&box64env && !wine_nx_perf25_copy(0x93df43,boot));
    wine_nx_vk_successful_presents=1;
    for(unsigned pass=0;pass<4;++pass) assert(!wine_nx_perf25_copy(0x93df43,boot));
    const void *game=pes22_select(0x93df43);
    assert(game==&pes21_env);
    for(unsigned pass=0;pass<4;++pass) assert(wine_nx_perf25_copy(0x93df43,game));
    assert(!wine_nx_perf25_copy(0x93df44,game));
    pes25_mode=0;assert(!wine_nx_perf25_copy(0x93df43,game));pes25_mode=1;
    pes17_identity=-1;assert(!wine_nx_perf25_copy(0x93df43,game));pes17_identity=1;
    code[20]^=1;assert(!wine_nx_perf25_copy(0x93df43,game));code[20]^=1;
    pes22_mode=1;const void *other=pes22_select(0x93df43);
    assert(other==&pes22_env && wine_nx_perf25_copy(0x93df43,other));
    unsigned char guest[42],native[64];memset(guest,0xab,sizeof(guest));memset(native,0xcd,sizeof(native));
    dynablock_t db={0};db.x64_addr=(void*)0x115c356;db.x64_readaddr=(uintptr_t)guest;db.x64_size=sizeof(guest);
    db.block=native;db.native_size=sizeof(native);db.is32bits=1;db.hash=123;
    memset(pes17_snapshots,0,sizeof(pes17_snapshots));pes17_capture=1;
    wine_nx_vk_successful_presents=0;
    wine_nx_perf25_completed(&db,&box64env);
    assert(pes17_snapshots[5].state==2 && pes17_snapshots[5].guest==0x115c356);
    assert(!memcmp(pes17_snapshots[5].x86,guest,sizeof(guest)));
    assert(!memcmp(pes17_snapshots[5].arm,native,sizeof(native)));
    memset(guest,0xef,sizeof(guest));wine_nx_perf25_completed(&db,&box64env);
    assert(pes17_snapshots[5].x86[0]==0xab); /* immutable */
    memset(pes17_snapshots,0,sizeof(pes17_snapshots));pes17_capture=0;
    wine_nx_perf25_completed(&db,&box64env);assert(!pes17_snapshots[5].state);
    pes17_capture=1;db.x64_size=0x19; /* stops exactly before fault PC */
    wine_nx_perf25_completed(&db,&box64env);assert(!pes17_snapshots[5].state);
    db.x64_size=42;db.is32bits=0;
    wine_nx_perf25_completed(&db,&box64env);assert(!pes17_snapshots[5].state);
    munmap(mapped,4096);wine_nx_perf25_report();
    puts("PERF25 stable four-pass selection, fallback, fingerprint and bounded pre-present capture PASS");
    return 0;
}
