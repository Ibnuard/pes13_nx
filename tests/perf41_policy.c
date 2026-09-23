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

#include "../local/perf41/pes13_perf21_capture.h"

void wine_nx_runtime_trace(const char *line) { (void)line; }

static void read_exact(const char *path, void *buffer, size_t length)
{
    FILE *file = fopen(path, "rb");
    assert(file);
    assert(fread(buffer, 1, length, file) == length);
    assert(fgetc(file) == EOF);
    fclose(file);
}

int main(int argc, char **argv)
{
    assert(argc == 3);
    unsigned char early[PES40_EARLY_BYTES], matrix[PES41_MATRIX_BYTES];
    read_exact(argv[1], early, sizeof early);
    read_exact(argv[2], matrix, sizeof matrix);
    assert(pes40_hash_bytes(early, sizeof early) == PES40_EARLY_FNV);
    assert(pes40_hash_bytes(matrix, sizeof matrix) == PES41_MATRIX_FNV);
    assert(PES41_MATRIX_END < (uintptr_t)0x112fb90u);

    void *page = mmap((void *)(uintptr_t)0x1120000, 0x20000,
                      PROT_READ | PROT_WRITE,
                      MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    assert(page != MAP_FAILED);
    memcpy((void *)PES40_EARLY_ADDR, early, sizeof early);
    memcpy((void *)PES41_MATRIX_ADDR, matrix, sizeof matrix);
    assert(pes40_match_early(PES40_EARLY_ADDR));
    assert(pes41_match_matrix(PES41_MATRIX_ADDR));
    assert(!pes41_match_matrix(PES41_MATRIX_ADDR + 1));

    box64env.dynarec_safeflags = 2;
    box64env.dynarec_strongmem = 1;
    box64env.dynarec_x87double = 1;
    box64env_t original = box64env;
    pes21_mode = 1;
    pes40_mode = 1;
    assert(pes21_select(PES40_EARLY_ADDR) == &pes21_env);
    assert(pes40_early_selected == 1);
    assert(pes21_select(PES41_MATRIX_ADDR) == &box64env);
    assert(pes41_selected == 0);

    pes41_mode = 1;
    ((unsigned char *)PES41_MATRIX_ADDR)[0] ^= 1;
    assert(pes21_select(PES41_MATRIX_ADDR) == &box64env);
    assert(pes41_rejected == 1 && pes41_selected == 0);
    ((unsigned char *)PES41_MATRIX_ADDR)[0] ^= 1;
    assert(pes21_select(PES41_MATRIX_ADDR) == &pes21_env);
    assert(pes41_selected == 1 && pes41_early_selected == 1);
    assert(pes21_env.dynarec_fastround == 1);
    assert(pes21_env.dynarec_safeflags == 2);
    assert(pes21_env.dynarec_x87double == 1);
    assert(pes21_env.dynarec_strongmem == 1);
    assert(!memcmp(&box64env, &original, sizeof original));
    assert(pes21_select((uintptr_t)0x112fb90u) == &box64env);
    assert(pes21_select(PES41_MATRIX_END) == &box64env);
    assert(pes21_select((uintptr_t)0xfa390000u) == &box64env);
    assert(wine_nx_perf21_block_end(PES41_MATRIX_ADDR, UINTPTR_MAX,
                                    &pes21_env) == PES41_MATRIX_END - 1);
    assert(wine_nx_perf21_block_end(PES41_MATRIX_ADDR, PES41_MATRIX_ADDR + 10,
                                    &pes21_env) == PES41_MATRIX_ADDR + 10);
    assert(wine_nx_perf21_block_end((uintptr_t)0x112fb90u, UINTPTR_MAX,
                                    &box64env) == UINTPTR_MAX);

    int block = 1;
    wine_nx_perf21_completed(&block, &pes21_env);
    assert(captured == 1 && pes21_completed == 1);
    wine_nx_vk_successful_presents = 1;
    assert(pes21_select(PES41_MATRIX_ADDR) == &pes21_env);
    assert(pes41_selected == 2 && pes41_early_selected == 1);
    wine_nx_perf21_report();
    wine_nx_perf40_report();
    wine_nx_perf41_report();
    assert(munmap(page, 0x20000) == 0);
    puts("PERF41 exact matrix sibling, fingerprint, PERF19 isolation PASS");
    return 0;
}
