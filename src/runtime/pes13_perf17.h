/* PERF17: an opt-in block-size experiment at the PERF16 guest hotspots.
 * Include after Box64's env and dynablock declarations. Compilation already
 * holds the translator mutex. No hooks are added to executed guest blocks. */
#ifndef PES13_PERF17_H
#define PES13_PERF17_H

#include <stdint.h>
#include <string.h>
#include <stdio.h>

extern unsigned int wine_nx_vk_successful_presents;
static box64env_t pes17_env;
static unsigned int pes17_selected, pes17_completed;
static int pes17_mode, pes17_capture = 1, pes17_identity;
static int pes17_env_ready;

/* VAs for the fixed-base EXE identified in docs/PERF17.md. These are pages
 * around measured instruction buckets, not guessed function boundaries. */
static const uintptr_t pes17_ranges[][2] = {
    {0x112f000, 0x1130000},
    {0x937000, 0x938000},
    {0x93b000, 0x93c000},
    {0x93c000, 0x93e000},
};
static const uintptr_t pes17_hot[][2] = {
    {0x112fb80, 0x112fde0}, {0x9379c0, 0x937a40},
    {0x93b840, 0x93b8c0}, {0x93cf80, 0x93d020},
};

static int pes17_region(uintptr_t addr)
{
    unsigned int i;
    for (i = 0; i < sizeof(pes17_ranges) / sizeof(pes17_ranges[0]); ++i)
        if (addr >= pes17_ranges[i][0] && addr < pes17_ranges[i][1]) return (int)i;
    return -1;
}

/* PERF17B binds the on-disk header to the loader's main image before guest
 * execution. Packed programs may subsequently rewrite their memory headers.
 * This remains a version check, not a cryptographic authenticity check. */
static uint32_t pes17_header_hash(const unsigned char *p, size_t size)
{
    uint32_t hash = 2166136261u;
    size_t i;
    if (size < 512) return 0;
    for (i = 0; i < 512; ++i) hash = (hash ^ p[i]) * 16777619u;
    return hash;
}

static int pes17_header_matches(const unsigned char *p, size_t size)
{
    return size >= 512 && p[0] == 'M' && p[1] == 'Z' &&
           pes17_header_hash(p, size) == 0x4e46d440u;
}

static int pes17_bind_header(const unsigned char *p, size_t size,
                             uintptr_t base, size_t image_size)
{
    int identity;
    if (base != 0x400000 || image_size != 0x189a000) identity = -2;
    else if (size < 512) identity = -3;
    else identity = pes17_header_matches(p, size) ? 1 : -1;
    __atomic_store_n(&pes17_identity, identity, __ATOMIC_RELEASE);
    return identity;
}

static int pes17_check_image(void)
{
    /* An unbound image is not a permanent failure. The loader publishes the
     * result before starting guest threads; never inspect mutable guest
     * headers or do file I/O under the translator mutex. */
    return __atomic_load_n(&pes17_identity, __ATOMIC_ACQUIRE) == 1;
}

static box64env_t *pes17_select(uintptr_t addr, box64env_t *fallback)
{
    if (!pes17_mode || pes17_region(addr) < 0 ||
        !__atomic_load_n(&wine_nx_vk_successful_presents, __ATOMIC_ACQUIRE) ||
        !pes17_check_image()) return fallback;
    if (!pes17_env_ready)
    {
        pes17_env = box64env;
        pes17_env.dynarec_bigblock = 1;
        pes17_env.is_dynarec_bigblock_overridden = 1;
        pes17_env.is_any_overridden = 1;
        pes17_env_ready = 1;
    }
    __atomic_add_fetch(&pes17_selected, 1, __ATOMIC_RELAXED);
    return &pes17_env;
}

/* Keep forward block extension inside the selected page range. A block that
 * starts elsewhere continues to use the baseline's end and environment. */
uintptr_t wine_nx_perf17_block_end(uintptr_t start, uintptr_t end, const void *env)
{
    int region = pes17_region(start);
    /* native_pass tests addr > end on a page transition: its end is inclusive. */
    if (env == &pes17_env && region >= 0 && end >= pes17_ranges[region][1])
        return pes17_ranges[region][1] - 1;
    return end;
}

#define PES17_SLOTS 8
#define PES17_X86_BYTES 8192
#define PES17_ARM_BYTES 8192

struct pes17_snapshot
{
    unsigned int state; /* 0 unused, 1 writing, 2 ready, 3 reported; no reuse */
    unsigned int region, bigblock, hash;
    uintptr_t guest, native;
    size_t guest_size, native_size, x86_bytes, arm_bytes;
    unsigned char x86[PES17_X86_BYTES], arm[PES17_ARM_BYTES];
};
static struct pes17_snapshot pes17_snapshots[PES17_SLOTS];
static unsigned int pes17_region_count[4], pes17_used;

/* Called at successful FillBlock completion, before publication and while
 * holding the translator mutex. Fixed buffers only: no allocation, I/O,
 * logging, pauses or additional locks on this path. */
void wine_nx_perf17_capture(void *opaque, unsigned int bigblock)
{
    dynablock_t *db = opaque;
    uintptr_t guest = (uintptr_t)db->x64_addr;
    int region = pes17_region(guest);
    unsigned int slot;
    struct pes17_snapshot *s;
    if (region < 0) return;
    if (bigblock == 1 && pes17_mode)
        __atomic_add_fetch(&pes17_completed, 1, __ATOMIC_RELAXED);
    if (!pes17_capture || pes17_used == PES17_SLOTS ||
        pes17_region_count[region] >= 2 || !db->x64_size ||
        !db->native_size || !db->is32bits || !pes17_check_image()) return;
    if (guest >= pes17_hot[region][1] ||
        (guest < pes17_hot[region][0] && db->x64_size <= pes17_hot[region][0] - guest)) return;
    /* Reserve one slot per region/policy. Early baseline translations cannot
     * consume the slot needed for a later optimized translation. */
    slot = (unsigned int)region * 2 + (bigblock == 1);
    s = &pes17_snapshots[slot];
    if (__atomic_load_n(&s->state, __ATOMIC_ACQUIRE)) return;
    ++pes17_used;
    __atomic_store_n(&s->state, 1, __ATOMIC_RELAXED);
    ++pes17_region_count[region];
    s->region = (unsigned int)region;
    s->bigblock = bigblock;
    s->hash = db->hash;
    s->guest = guest;
    s->native = (uintptr_t)db->block;
    s->guest_size = db->x64_size;
    s->native_size = db->native_size;
    s->x86_bytes = db->x64_size < PES17_X86_BYTES ? db->x64_size : PES17_X86_BYTES;
    s->arm_bytes = db->native_size < PES17_ARM_BYTES ? db->native_size : PES17_ARM_BYTES;
    memcpy(s->x86, (const void *)db->x64_readaddr, s->x86_bytes);
    memcpy(s->arm, DynarecMapWritableAddress(db->block), s->arm_bytes);
    __atomic_store_n(&s->state, 2, __ATOMIC_RELEASE);
}

/* Only the existing log thread calls this. Each snapshot is immutable after
 * publication, so it can be formatted after the translator resumes. */
static void pes17_hex(unsigned int slot, const char *kind, const unsigned char *bytes, size_t size)
{
    static const char hex[] = "0123456789abcdef";
    size_t offset;
    char line[220];
    for (offset = 0; offset < size; offset += 64)
    {
        size_t i, n = size - offset < 64 ? size - offset : 64;
        int used = snprintf(line, sizeof(line), "[PERF17-CODE] slot=%u kind=%s off=%lu hex=",
                            slot, kind, (unsigned long)offset);
        for (i = 0; i < n; ++i)
        {
            line[used++] = hex[bytes[offset + i] >> 4];
            line[used++] = hex[bytes[offset + i] & 15];
        }
        line[used] = 0;
        if (&wine_nx_runtime_trace) wine_nx_runtime_trace(line);
    }
}

void wine_nx_perf17_report(void)
{
    unsigned int i;
    char line[320];
    snprintf(line, sizeof(line), "[PERF17] hotblocks=%d identity=%d selected=%u completed=%u capture=%d",
             __atomic_load_n(&pes17_mode, __ATOMIC_ACQUIRE), __atomic_load_n(&pes17_identity, __ATOMIC_ACQUIRE),
             __atomic_load_n(&pes17_selected, __ATOMIC_RELAXED),
             __atomic_load_n(&pes17_completed, __ATOMIC_RELAXED), __atomic_load_n(&pes17_capture, __ATOMIC_ACQUIRE));
    if (&wine_nx_runtime_trace) wine_nx_runtime_trace(line);
    for (i = 0; i < PES17_SLOTS; ++i)
    {
        struct pes17_snapshot *s = &pes17_snapshots[i];
        if (__atomic_load_n(&s->state, __ATOMIC_ACQUIRE) != 2) continue;
        snprintf(line, sizeof(line),
                 "[PERF17-BLOCK] slot=%u region=%u bigblock=%u guest=%lx guest_size=%lu native=%lx native_size=%lu hash=%08x x86_bytes=%lu arm_bytes=%lu",
                 i, s->region, s->bigblock, (unsigned long)s->guest, (unsigned long)s->guest_size,
                 (unsigned long)s->native, (unsigned long)s->native_size, s->hash,
                 (unsigned long)s->x86_bytes, (unsigned long)s->arm_bytes);
        if (&wine_nx_runtime_trace) wine_nx_runtime_trace(line);
        pes17_hex(i, "x86", s->x86, s->x86_bytes);
        pes17_hex(i, "arm64", s->arm, s->arm_bytes);
        __atomic_store_n(&s->state, 3, __ATOMIC_RELEASE);
    }
}

#endif
