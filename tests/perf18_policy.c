#define main perf17_policy_main
#define wine_nx_runtime_trace perf17_test_trace
#include "perf17_policy.c"
#undef main
#undef wine_nx_runtime_trace
void wine_nx_runtime_trace(const char *text) __attribute__((weak));
#include "../src/runtime/pes13_perf18.h"
void wine_nx_runtime_trace(const char *text) { perf17_test_trace(text); }
int main(int argc, char **argv)
{
    assert(!perf17_policy_main(argc, argv));
    pes18_mode = 1;
    pes17_identity = -1;
    assert(!wine_nx_perf18_round_site(0x112fb90, 3));
    pes17_identity = 1;
    assert(!wine_nx_perf18_round_site(0x112fb8f, 3));
    assert(!wine_nx_perf18_round_site(0x112fe20, 3));
    assert(!wine_nx_perf18_round_site(0xfa000000, 3));
    assert(wine_nx_perf18_round_site(0x112fb90, 0));
    assert(!pes18_sites && !pes18_matrix_sites);
    assert(wine_nx_perf18_round_site(0x112fb90, 3));
    assert(wine_nx_perf18_round_site(0x937990, 3));
    assert(wine_nx_perf18_round_site(0x93b83b, 3));
    assert(wine_nx_perf18_round_site(0x93cff0, 3));
    assert(pes18_sites == 4 && pes18_matrix_sites == 1);
    pes18_mode = 0;
    assert(!wine_nx_perf18_round_site(0x112fb90, 3));
    wine_nx_perf18_report();
    puts("PERF18 scope/identity/control and generation counters PASS");
    return 0;
}
