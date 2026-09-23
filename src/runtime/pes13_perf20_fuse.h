/* Conservative, size-preserving fusion of Box64 x87 rounding guards.
 * Pure C so the exact production pass can also be tested on the host.
 * Unknown instructions break a run. Control flow rejects the entire block.
 * No code is modified until the whole block's control flow is checked. */
#ifndef PES13_PERF20_FUSE_H
#define PES13_PERF20_FUSE_H
#include <stddef.h>
#include <stdint.h>

struct pes20_result { unsigned int guards, merged, runs, flow_rejected; };

static int pes20_guest_reg(unsigned int r) { return r >= 10 && r <= 27; }

/* All accepted gap operations are independent of FPCR rounding mode and
 * cannot read/write the guard's scratch GPRs x1/x2/x4/x5 or emulator state.
 * Memory accesses are through guest registers; xEmu-relative writes stop a
 * run. Guest/native-emulator-state aliasing is outside the guest ABI. */
static int pes20_gap(uint32_t w)
{
    unsigned int rd = w & 31, rn = (w >> 5) & 31;
    uint32_t op;
    if (w == 0xd503201f) return 1; /* NOP */
    op = w & 0xfffffc00;
    if (op == 0x1e22c000 || /* FCVT Dn, Sm: exact widening */
        op == 0x1e204000 || op == 0x1e604000 || /* FMOV scalar */
        op == 0x1e20c000 || op == 0x1e60c000 || /* FABS */
        op == 0x1e214000 || op == 0x1e614000) return 1; /* FNEG */
    /* Unsigned-offset LDR/STR or unscaled LDUR/STUR, no writeback. */
    op = w & 0xffc00000;
    if (op == 0xbd000000 || op == 0xbd400000 ||
        op == 0xfd000000 || op == 0xfd400000 ||
        op == 0x3d800000 || op == 0x3dc00000)
        return pes20_guest_reg(rn);
    if (op == 0xb9000000 || op == 0xb9400000 ||
        op == 0xf9000000 || op == 0xf9400000)
        return pes20_guest_reg(rn) && pes20_guest_reg(rd);
    op = w & 0xffe00c00;
    if (op == 0xbc000000 || op == 0xbc400000 ||
        op == 0xfc000000 || op == 0xfc400000 ||
        op == 0x3c800000 || op == 0x3cc00000)
        return pes20_guest_reg(rn);
    if (op == 0xb8000000 || op == 0xb8400000 ||
        op == 0xf8000000 || op == 0xf8400000)
        return pes20_guest_reg(rn) && pes20_guest_reg(rd);
    /* ADD/SUB immediate without flag update. */
    op = w & 0xff800000;
    if (op == 0x11000000 || op == 0x51000000 ||
        op == 0x91000000 || op == 0xd1000000)
        return pes20_guest_reg(rd) && pes20_guest_reg(rn);
    /* MOV GPR (ORR Rd, ZR, Rm, LSL #0). */
    op = w & 0xffe0ffe0;
    if (op == 0x2a0003e0 || op == 0xaa0003e0)
        return pes20_guest_reg(rd) && pes20_guest_reg((w >> 16) & 31);
    return 0;
}

static int pes20_arithmetic(uint32_t w)
{
    uint32_t op = w & 0xffe0fc00;
    /* Scalar single/double FMUL, FDIV, FADD, FSUB. No GPR side effects. */
    if (op == 0x1e200800 || op == 0x1e600800 ||
        op == 0x1e201800 || op == 0x1e601800 ||
        op == 0x1e202800 || op == 0x1e602800 ||
        op == 0x1e203800 || op == 0x1e603800) return 1;
    op = w & 0xfffffc00;
    return op == 0x1e624000 || /* FCVT Sn, Dm */
           op == 0x1e21c000 || op == 0x1e61c000; /* FSQRT */
}

/* Recognize the complete pinned emitter sequence, not a loose opcode hit.
 * Return the scratch variant. Different variants are never merged. */
static unsigned int pes20_guard(const uint32_t *c, size_t left)
{
    if (left < 10 || c[0] != 0xb9431c01 || c[1] != 0x330a2c21 ||
        c[4] != 0xd53b4401 || c[5] != 0xaa0103e4 ||
        c[7] != 0xd51b4401 || !pes20_arithmetic(c[8]) ||
        c[9] != 0xd51b4404) return 0;
    if (c[2] == 0x53010425 && c[3] == 0x331f0025 && c[6] == 0xb36a04a1) return 5;
    if (c[2] == 0x53010422 && c[3] == 0x331f0022 && c[6] == 0xb36a0441) return 2;
    return 0;
}

static int pes20_branch(uint32_t w)
{
    return (w & 0x7c000000) == 0x14000000 || /* B/BL */
           (w & 0xff000000) == 0x54000000 || /* B.cond */
           (w & 0x7e000000) == 0x34000000 || /* CBZ/CBNZ */
           (w & 0x7e000000) == 0x36000000 || /* TBZ/TBNZ */
           (w & 0xfe000000) == 0xd6000000;   /* register branch/call/return */
}

static struct pes20_result pes20_fuse(uint32_t *c, size_t bytes)
{
    struct pes20_result r = {0};
    size_t n = bytes / 4, i, last = 0;
    unsigned int variant = 0, run_length = 0, gap = 0;
    if (!bytes || bytes % 4 || bytes > 65536) return r;
    /* The real emitter's final dispatch is BR x2, optionally followed by
     * one alignment word. Reject any other branch, even outside a run:
     * this rules out alternate entries/back-edges into skipped guards. */
    for (i = 0; i < n; ++i) {
        if (!pes20_branch(c[i])) continue;
        if (c[i] == 0xd61f0040 && (i+1 == n ||
            (i+2 == n && (c[i+1] == 0 || c[i+1] == 0xffffffff || c[i+1] == 0xd503201f)))) continue;
        r.flow_rejected = 1;
        return r;
    }
    for (i = 0; i < n;) {
        unsigned int current = pes20_guard(c+i, n-i);
        if (current) {
            ++r.guards;
            if (variant == current && gap <= 32) {
                /* Skip the next eight setup instructions. Preserve every
                 * native offset and the original instructions behind it. */
                c[i] = 0x14000008;
                c[last] = last+1 == i ? 0x14000009 : 0xd503201f;
                ++r.merged;
                if (run_length == 1) ++r.runs;
                ++run_length;
            } else run_length = 1;
            variant = current;
            last = i+9;
            gap = 0;
            i += 10;
        } else {
            if (!pes20_gap(c[i]) || ++gap > 32) { variant = 0; run_length = 0; }
            ++i;
        }
    }
    return r;
}
#endif
