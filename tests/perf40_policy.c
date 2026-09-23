#define _GNU_SOURCE
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>

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

#include "../local/perf40/pes13_perf21_capture.h"

void wine_nx_runtime_trace(const char *line) { (void)line; }

int main(int argc, char **argv)
{
    assert(argc == 2);
    FILE *file = fopen(argv[1], "rb");
    assert(file);
    unsigned char guest[PES40_EARLY_BYTES];
    assert(fread(guest, 1, sizeof guest, file) == sizeof guest);
    assert(fgetc(file) == EOF);
    fclose(file);
    assert(pes40_hash_bytes(guest, sizeof guest) == PES40_EARLY_FNV);

    void *page = mmap((void *)(PES40_EARLY_ADDR & ~(uintptr_t)0xffff), 0x10000,
                      PROT_READ | PROT_WRITE,
                      MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    assert(page != MAP_FAILED);
    memcpy((void *)PES40_EARLY_ADDR, guest, sizeof guest);
    assert(pes40_match_early(PES40_EARLY_ADDR));
    assert(!pes40_match_early(PES40_EARLY_ADDR + 1));

    box64env.dynarec_safeflags = 2;
    box64env.dynarec_strongmem = 1;
    box64env.dynarec_x87double = 1;
    box64env_t original = box64env;
    pes21_mode = 1;
    assert(pes21_select(PES40_EARLY_ADDR) == &box64env);
    assert(pes21_boot_fallback == 1 && !pes40_early_selected);

    pes40_mode = 1;
    ((unsigned char *)PES40_EARLY_ADDR)[0] ^= 1;
    assert(pes21_select(PES40_EARLY_ADDR) == &box64env);
    assert(pes40_early_rejected == 1 && pes21_boot_fallback == 2);
    ((unsigned char *)PES40_EARLY_ADDR)[0] ^= 1;
    assert(pes21_select(PES40_EARLY_ADDR) == &pes21_env);
    assert(pes40_early_selected == 1 && pes21_active == 1);
    assert(pes21_env.dynarec_fastround == 1);
    assert(pes21_env.dynarec_safeflags == 2);
    assert(pes21_env.dynarec_x87double == 1);
    assert(pes21_env.dynarec_strongmem == 1);
    assert(!memcmp(&box64env, &original, sizeof original));
    assert(pes21_select(0x112f8f0) == &box64env);
    assert(pes21_select(0x112fb90) == &box64env);
    assert(pes21_select(0xfa390000) == &box64env);
    assert(pes21_select(0x113027c) == &box64env);
    assert(wine_nx_perf21_block_end(PES40_EARLY_ADDR, UINTPTR_MAX,
                                    &pes21_env) == PES21_TEXT_END - 1);
    int block = 1;
    wine_nx_perf21_completed(&block, &pes21_env);
    assert(captured == 1 && pes21_completed == 1);
    wine_nx_vk_successful_presents = 1;
    assert(pes21_select(0x113120c) == &pes21_env);
    wine_nx_perf21_report();
    wine_nx_perf40_report();
    assert(munmap(page, 0x10000) == 0);
    puts("PERF40 exact pre-present FASTROUND, fingerprint, matrix/DLL boundaries PASS");
    return 0;
}
