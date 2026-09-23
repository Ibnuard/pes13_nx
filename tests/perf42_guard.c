/* Replays the captured PERF28 PES13 failure and rejects nearby faults. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../src/runtime/pes13_perf42_guard.h"

enum { CODE_BASE = 0x0115c300, STACK_BASE = 0x0219fca4 };
static unsigned char code[256], stack[128];

static int fixture_read(void *opaque, uint32_t at, void *out, size_t size)
{
    (void)opaque;
    if (at >= CODE_BASE && at - CODE_BASE <= sizeof code &&
        size <= sizeof code - (at - CODE_BASE))
    {
        memcpy(out, code + at - CODE_BASE, size);
        return 1;
    }
    if (at >= STACK_BASE && at - STACK_BASE <= sizeof stack &&
        size <= sizeof stack - (at - STACK_BASE))
    {
        memcpy(out, stack + at - STACK_BASE, size);
        return 1;
    }
    return 0;
}

static void load(const char *path, void *out, size_t size)
{
    FILE *file = fopen(path, "rb");
    assert(file && fread(out, 1, size, file) == size);
    assert(fgetc(file) == EOF);
    fclose(file);
}

int main(int argc, char **argv)
{
    assert(argc == 3);
    load(argv[1], code, sizeof code);
    load(argv[2], stack, sizeof stack);
    struct pes42_fault f = {
        .status=0xc0000005, .address=4, .access=0,
        .eip=PES42_FAULT_PC, .esp=STACK_BASE, .eax=0,
        .esi=4, .ebp=PES42_KEY, .edi=0x02c6a34c, .identity=1,
    };
    uint32_t resume = 0;
    assert(pes42_decide(&f, fixture_read, NULL, &resume));
    assert(resume == PES42_RESUME_PC);
    resume = 0xdeadbeef;
    f.identity = 0;
    assert(!pes42_decide(&f, fixture_read, NULL, &resume));
    f.identity = 1; f.address = 8;
    assert(!pes42_decide(&f, fixture_read, NULL, &resume));
    f.address = 4; f.ebp = 0x4088;
    assert(!pes42_decide(&f, fixture_read, NULL, &resume));
    f.ebp = PES42_KEY; f.eip = PES42_FAULT_PC + 2;
    assert(!pes42_decide(&f, fixture_read, NULL, &resume));
    f.eip = PES42_FAULT_PC; code[PES42_FAULT_PC - CODE_BASE] ^= 1;
    assert(!pes42_decide(&f, fixture_read, NULL, &resume));
    assert(resume == 0xdeadbeef);
    puts("PERF42 captured startup fault recognized; adjacent faults unchanged PASS");
    return 0;
}
