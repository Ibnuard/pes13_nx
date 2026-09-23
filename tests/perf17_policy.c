#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "env.h"
#include "dynarec/dynablock_private.h"

box64env_t box64env;
unsigned int wine_nx_vk_successful_presents;
static unsigned int code_lines, block_lines, report_lines;
void wine_nx_runtime_trace(const char *text) __attribute__((weak));
void *DynarecMapWritableAddress(void *p) { return p; }
#include "../src/runtime/pes13_perf17.h"
void wine_nx_runtime_trace(const char *text)
{
    assert(strlen(text) < 320);
    if (strstr(text, "[PERF17-CODE]")) ++code_lines;
    else if (strstr(text, "[PERF17-BLOCK]")) ++block_lines;
    else ++report_lines;
}

int main(int argc, char **argv)
{
    box64env_t original, expected, *selected;
    unsigned char guest[16384], native[16384], first[512];
    dynablock_t db = {0};
    unsigned int i, before;
    FILE *f;
    assert(argc == 2);
    f = fopen(argv[1], "rb"); assert(f);
    assert(fread(first, 1, sizeof(first), f) == sizeof(first)); fclose(f);
    assert(pes17_header_matches(first, sizeof(first)));
    assert(!pes17_header_matches(first, sizeof(first) - 1));
    assert(!pes17_check_image()); /* unbound is a temporary baseline fallback */
    assert(pes17_bind_header(first, 511, 0x400000, 0x189a000) == -3);
    assert(!pes17_check_image());
    assert(pes17_bind_header(first, 512, 0x500000, 0x189a000) == -2);
    assert(pes17_bind_header(first, 512, 0x400000, 0x1899000) == -2);
    assert(pes17_bind_header(first, 512, 0x400000, 0x189a000) == 1);
    first[300] ^= 1;
    assert(!pes17_header_matches(first, sizeof(first)));
    assert(pes17_check_image()); /* later changes to guest headers cannot unbind */
    assert(pes17_bind_header(first, 512, 0x400000, 0x189a000) == -1);
    assert(!pes17_check_image()); /* different file remains rejected */
    first[300] ^= 1;
    assert(pes17_bind_header(first, 512, 0x400000, 0x189a000) == 1);
    box64env.dynarec_safeflags = 2;
    box64env.dynarec_strongmem = 1;
    box64env.dynarec_x87double = 1;
    box64env.dynarec_wait = 1;
    original = box64env;
    pes17_mode = 1;
    pes17_identity = 1;
    assert(pes17_select(0x112fba0, &box64env) == &box64env); /* before present */
    wine_nx_vk_successful_presents = 1;
    pes17_mode = 0;
    assert(pes17_select(0x112fba0, &box64env) == &box64env); /* control */
    pes17_mode = 1;
    pes17_identity = -1;
    assert(pes17_select(0x112fba0, &box64env) == &box64env); /* unknown image */
    pes17_identity = 1;
    for (i = 0; i < 4; ++i)
    {
        uintptr_t low = pes17_ranges[i][0], high = pes17_ranges[i][1];
        assert(pes17_region(low) == (int)i && pes17_region(high - 1) == (int)i);
        assert(pes17_region(high) != (int)i);
        selected = pes17_select(low, &box64env);
        assert(selected != &box64env);
        expected = original;
        expected.dynarec_bigblock = 1;
        expected.is_dynarec_bigblock_overridden = 1;
        expected.is_any_overridden = 1;
        assert(!memcmp(selected, &expected, sizeof(expected)));
        assert(wine_nx_perf17_block_end(low, UINTPTR_MAX, selected) == high - 1);
        assert(wine_nx_perf17_block_end(low, high, selected) == high - 1);
        assert(wine_nx_perf17_block_end(low, low + 16, selected) == low + 16);
        assert(wine_nx_perf17_block_end(low, UINTPTR_MAX, &box64env) == UINTPTR_MAX);
    }
    assert(pes17_select(0x112efff, &box64env) == &box64env);
    assert(pes17_select(0x1130000, &box64env) == &box64env);
    assert(pes17_select(0x70000000, &box64env) == &box64env);
    assert(!memcmp(&box64env, &original, sizeof(original)));
    memset(guest, 0x90, sizeof(guest)); memset(native, 0x1f, sizeof(native));
    db.x64_readaddr = (uintptr_t)guest; db.x64_size = sizeof(guest);
    db.block = native; db.native_size = sizeof(native); db.is32bits = 1;
    for (i = 0; i < 4; ++i)
    {
        db.x64_addr = (void *)pes17_ranges[i][0]; db.hash = 100 + i;
        wine_nx_perf17_capture(&db, 0);
        before = pes17_used;
        wine_nx_perf17_capture(&db, 0); /* identical block is not copied twice */
        assert(pes17_used == before);
        db.hash += 20; wine_nx_perf17_capture(&db, 0);
        assert(pes17_used == before); /* baseline cannot exhaust optimized slot */
        wine_nx_perf17_capture(&db, 1);
        db.hash += 20; wine_nx_perf17_capture(&db, 1);
        assert(pes17_region_count[i] == 2);
    }
    assert(pes17_used == 8 && !code_lines && !block_lines && !report_lines);
    for (i = 0; i < PES17_SLOTS; ++i)
    {
        assert(pes17_snapshots[i].state == 2);
        assert(pes17_snapshots[i].x86_bytes == PES17_X86_BYTES);
        assert(pes17_snapshots[i].arm_bytes == PES17_ARM_BYTES);
        assert(!memcmp(pes17_snapshots[i].x86, guest, PES17_X86_BYTES));
        assert(!memcmp(pes17_snapshots[i].arm, native, PES17_ARM_BYTES));
    }
    memset(guest, 0xcc, sizeof(guest)); memset(native, 0, sizeof(native));
    assert(pes17_snapshots[0].x86[0] == 0x90); /* independent immutable copy */
    wine_nx_perf17_report();
    assert(block_lines == 8 && code_lines == 8 * (PES17_X86_BYTES + PES17_ARM_BYTES) / 64);
    before = code_lines; wine_nx_perf17_report(); assert(code_lines == before);
    puts("PERF17: boundaries, identity, startup/control, unchanged preset, bounded copies and one-shot reporting PASS");
    return 0;
}
