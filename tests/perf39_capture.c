#include <assert.h>
#include <stdint.h>
#include <stdio.h>

typedef struct {
    int dynarec_fastround;
    int dynarec_safeflags;
    int dynarec_fastnan;
    int dynarec_x87double;
    int dynarec_strongmem;
    int dynarec_bigblock;
    int dynarec_callret;
    int is_dynarec_fastround_overridden;
    int is_any_overridden;
} box64env_t;

static box64env_t box64env;
unsigned int wine_nx_vk_successful_presents;
static unsigned int captured;
static int pes17_check_image(void) { return 1; }
static void wine_nx_perf20_capture(void *block) { assert(block); ++captured; }
void wine_nx_runtime_trace(const char *line) __attribute__((weak));

#include "../local/perf39/pes13_perf21_capture.h"

void wine_nx_runtime_trace(const char *line) { (void)line; }

int main(void)
{
    int block = 1;
    pes21_mode = 1;
    assert(pes21_select(0x113027b) == &box64env); /* before first present */
    wine_nx_perf21_completed(&block, &box64env);
    assert(captured == 1 && pes21_completed == 0);

    wine_nx_vk_successful_presents = 1;
    assert(pes21_select(0x112f8f0) == &box64env); /* excluded matrix page */
    wine_nx_perf21_completed(&block, &box64env);
    assert(captured == 2 && pes21_completed == 0);

    assert(pes21_select(0x113027b) == &pes21_env);
    wine_nx_perf21_completed(&block, &pes21_env);
    assert(captured == 3 && pes21_completed == 1);
    assert(wine_nx_perf21_block_end(0x112f8f0, UINTPTR_MAX, &box64env) == UINTPTR_MAX);
    wine_nx_perf21_report();
    return 0;
}
