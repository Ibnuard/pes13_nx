/* PES13 startup lookup recovery. This is only a decision: the caller updates
 * the returned guest context after Box64 has unwound an access violation.
 * A different image, instruction stream or guest state preserves the fault. */
#ifndef PES13_PERF42_GUARD_H
#define PES13_PERF42_GUARD_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>

#define PES42_FAULT_PC UINT32_C(0x0115c36f)
#define PES42_RESUME_PC UINT32_C(0x0115c3b9)
#define PES42_START_PC UINT32_C(0x0115c356)
#define PES42_KEY UINT32_C(0x0386)
#define PES42_MAX_RECOVERIES 4u

struct pes42_fault {
    uint32_t status, address, access, eip, esp, eax, esi, ebp, edi;
    int identity;
};
typedef int (*pes42_read_fn)(void *, uint32_t, void *, size_t);

static int pes42_decide(const struct pes42_fault *f, pes42_read_fn read,
                        void *opaque, uint32_t *resume)
{
    /* The first signature spans the lookup return and failing null read;
     * the second verifies the loop's next-input continuation. */
    static const unsigned char signature[] = {
        0x83,0xc4,0x08,0x3b,0xc6,0x74,0x05,0x66,0x39,0x28,0x74,0x02,
        0x33,0xc0,0x8d,0x70,0x04,0xc7,0x44,0x24,0x14,0,0,0,0,0x8b,0x2e,
        0x85,0xed
    };
    static const unsigned char continuation[] = {
        0x8b,0x44,0x24,0x18,0x8b,0x4c,0x24,0x2c,0x83,0xc0,0x02
    };
    unsigned char actual[sizeof(signature)], after[sizeof(continuation)];
    uint32_t index = UINT32_MAX, cursor = 0, list = 0;
    if (!f || !read || !resume || !f->identity ||
        f->status != UINT32_C(0xc0000005) || f->address != 4 || f->access != 0 ||
        f->eip != PES42_FAULT_PC || f->eax != 0 || f->esi != 4 ||
        f->ebp != PES42_KEY || !f->edi || f->esp > UINT32_MAX - 0x30)
        return 0;
    if (!read(opaque, PES42_START_PC, actual, sizeof actual) ||
        memcmp(actual, signature, sizeof signature) ||
        !read(opaque, PES42_RESUME_PC, after, sizeof after) ||
        memcmp(after, continuation, sizeof continuation) ||
        !read(opaque, f->esp + 0x14, &index, sizeof index) || index != 0 ||
        !read(opaque, f->esp + 0x18, &cursor, sizeof cursor) || !cursor ||
        !read(opaque, f->esp + 0x2c, &list, sizeof list) || !list)
        return 0;
    *resume = PES42_RESUME_PC;
    return 1;
}
#endif
