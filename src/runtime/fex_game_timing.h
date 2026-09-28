/* LGPL-2.1-or-later. Read-only snapshots of the supported PES13 image.
 * Addresses are not used until three code signatures match. The reader must
 * validate VM permissions and hold the VM lock while copying; no raw guest
 * pointer dereferences, writes, executable hooks or thread suspension here. */
#ifndef PES13_FEX_GAME_TIMING_H
#define PES13_FEX_GAME_TIMING_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>

typedef int (*fex_game_reader)(uint32_t, void *, size_t);
struct fex_game_timing {
    uint32_t object_address, object[17], display[11], pacer[56];
    uint16_t settings;
};

static uint64_t fex_game_u64(const uint32_t *p)
{
    return (uint64_t)p[0] | (uint64_t)p[1] << 32;
}

/* Check every snapshot: do not retain a validated pointer across guest frees
 * or resets. These reads do not constitute a coherent multi-thread snapshot. */
static int fex_game_snapshot(fex_game_reader read, struct fex_game_timing *out)
{
    static const struct { uint32_t address; unsigned char bytes[16]; } signatures[] = {
        {0x01119a60, {0x55,0x8b,0xec,0x83,0xe4,0xf8,0x83,0xec,0x38,0xa1,0x40,0x41,0x5b,0x01,0x33,0xc4}},
        {0x01118170, {0x6a,0xff,0x68,0x4b,0xc9,0x33,0x01,0x64,0xa1,0x00,0x00,0x00,0x00,0x50,0x53,0x55}},
        {0x0113ee10, {0x51,0xd9,0xee,0xd8,0x1d,0xc8,0xe5,0x8a,0x01,0xdf,0xe0,0xf6,0xc4,0x41,0x7a,0x07}},
    };
    struct fex_game_timing s = {0};
    unsigned char code[16];
    uint32_t after = 0;
    unsigned i;
    for (i = 0; i < sizeof(signatures) / sizeof(signatures[0]); ++i) {
        if (!read(signatures[i].address, code, sizeof(code))) return 0;
        if (memcmp(code, signatures[i].bytes, sizeof(code))) return -1;
    }
    if (!read(0x019bd154, &s.object_address, sizeof(s.object_address))) return 0;
    if (s.object_address < 0x10000 || (s.object_address & 3) ||
        s.object_address > UINT32_MAX - sizeof(s.object)) return 0;
    if (!read(s.object_address, s.object, sizeof(s.object))) return 0;
    if (s.object[0] != 0x01503540) return -2;
    if (!read(0x018ae358, s.display, sizeof(s.display)) ||
        !read(0x018ae4f8, s.pacer, sizeof(s.pacer)) ||
        !read(0x019bc826, &s.settings, sizeof(s.settings)) ||
        !read(0x019bd154, &after, sizeof(after))) return 0;
    if (after != s.object_address) return -3;
    *out = s;
    return 1;
}

/* Timestamps written by the game's own QPC -> microseconds conversion.
 * This is a last-frame timestamp, NOT a fresh QPC read or a simulation tick.
 * Readiness and bounds checks prevent interpreting uninitialized ring data. */
static uint64_t fex_game_ring_time(const struct fex_game_timing *s)
{
    uint32_t last = s->pacer[0x84 / 4], count = s->pacer[0x88 / 4];
    if (last >= 16 || !count || count > 16) return 0;
    return fex_game_u64(s->pacer + last * 2);
}

static uint64_t fex_game_ring_gap(const struct fex_game_timing *s)
{
    uint32_t last = s->pacer[0x84 / 4], count = s->pacer[0x88 / 4];
    uint64_t sum = 0;
    unsigned i;
    if (last >= 16 || count < 2 || count > 16) return 0;
    for (i = 0; i < count - 1; ++i) {
        uint64_t a = fex_game_u64(s->pacer + ((last - i) & 15) * 2);
        uint64_t b = fex_game_u64(s->pacer + ((last - i - 1) & 15) * 2);
        if (!b || a < b || a - b > 1000000) return 0;
        sum += a - b;
    }
    return sum / (count - 1);
}
#endif
