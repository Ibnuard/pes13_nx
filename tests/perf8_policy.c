#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "env.h"

box64env_t box64env;
unsigned int wine_nx_vk_successful_presents;
static unsigned int logs;
void wine_nx_runtime_trace(const char *msg) __attribute__((weak));
#include "../src/runtime/pes13_perf8_profile.h"
void wine_nx_runtime_trace(const char *msg) { assert(strstr(msg, "active")); ++logs; }

int main(int argc, char **argv)
{
    box64env_t original;
    char status[320];
    struct { box64env_t *env; } block, *dyn = &block;
    (void)argv;
    box64env.dynarec_safeflags = 2;
    box64env.dynarec_strongmem = 1;
    box64env.dynarec_x87double = 1;
    original = box64env;
    if (argc > 1) pes13_perf8_enabled = 0;
    block.env = pes13_perf8_select_env(0x400000);
    assert(block.env == &box64env && !logs);
    assert(BOX64DRENV(dynarec_bigblock) == 0);
    wine_nx_vk_successful_presents = 1;
    block.env = pes13_perf8_select_env(0x500000);
    if (pes13_perf8_enabled)
    {
        assert(block.env != &box64env && logs == 1);
        assert(BOX64DRENV(dynarec_bigblock) == 1);
        assert(block.env->dynarec_safeflags == 2);
        assert(block.env->dynarec_strongmem == 1);
        assert(block.env->dynarec_fastnan == 0 && block.env->dynarec_fastround == 0);
        assert(pes13_perf8_select_env(0x600000) == block.env && logs == 1);
        assert(pes13_perf8_builds == 2);
    }
    else assert(block.env == &box64env && !logs && !pes13_perf8_builds);
    assert(!memcmp(&original, &box64env, sizeof(original)));
    wine_nx_box64_profile_status(status, sizeof(status));
    assert(strstr(status, pes13_perf8_enabled ? "active=1" : "active=0"));
    puts(status);
    return 0;
}
