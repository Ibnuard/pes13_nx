/* Include after PERF17/19 declarations. All mutations happen before the
 * existing cache flush/publication, under the translator mutex. */
#include "pes13_perf20_fuse.h"
static int pes20_mode;
static unsigned int pes20_seen, pes20_blocks, pes20_guards, pes20_merged;
static unsigned int pes20_runs, pes20_flow, pes20_scope;

void wine_nx_perf20_patch(void *opaque)
{
    dynablock_t *db = opaque;
    uintptr_t guest = (uintptr_t)db->x64_addr;
    struct pes20_result r;
    if (!pes20_mode || !pes17_check_image() || !db->is32bits ||
        guest < 0x400000 || guest >= 0x1c9a000 ||
        !db->x64_size || db->x64_size > 0x1c9a000-guest ||
        guest == 0x112fb90) return; /* retain the hardware-verified PERF19 patch */
    __atomic_add_fetch(&pes20_seen, 1, __ATOMIC_RELAXED);
    if (db->sep_size || db->callret_size || !db->block || !db->native_size ||
        db->native_size % 4 || db->native_size > 65536) {
        __atomic_add_fetch(&pes20_scope, 1, __ATOMIC_RELAXED);
        return;
    }
    r = pes20_fuse(db->block, db->native_size);
    __atomic_add_fetch(&pes20_guards, r.guards, __ATOMIC_RELAXED);
    __atomic_add_fetch(&pes20_merged, r.merged, __ATOMIC_RELAXED);
    __atomic_add_fetch(&pes20_runs, r.runs, __ATOMIC_RELAXED);
    __atomic_add_fetch(&pes20_flow, r.flow_rejected, __ATOMIC_RELAXED);
    if (r.merged) __atomic_add_fetch(&pes20_blocks, 1, __ATOMIC_RELAXED);
}

/* Eight exact sampled 32-byte buckets from the PERF19 result. The old
 * broad ranges captured preceding blocks and missed the actual hotspots.
 * Reuse the bounded immutable snapshot format and log-thread serializer. */
static const uintptr_t pes20_targets[PES17_SLOTS] = {
    0x93b860, 0x93df40, 0x937a00, 0x93cfc0,
    0x93e4e0, 0x923080, 0x1131240, 0x1120400,
};

void wine_nx_perf20_capture(void *opaque)
{
    dynablock_t *db = opaque;
    uintptr_t guest = (uintptr_t)db->x64_addr;
    unsigned int i;
    if (!pes17_capture || !pes17_check_image() || !db->is32bits ||
        !db->x64_size || !db->native_size) return;
    for (i = 0; i < PES17_SLOTS; ++i) {
        struct pes17_snapshot *s = &pes17_snapshots[i];
        if (guest >= pes20_targets[i]+32 ||
            (guest < pes20_targets[i] && db->x64_size <= pes20_targets[i]-guest) ||
            __atomic_load_n(&s->state, __ATOMIC_ACQUIRE)) continue;
        __atomic_store_n(&s->state, 1, __ATOMIC_RELAXED);
        s->region = i; s->bigblock = 0; s->hash = db->hash;
        s->guest = guest; s->native = (uintptr_t)db->block;
        s->guest_size = db->x64_size; s->native_size = db->native_size;
        s->x86_bytes = db->x64_size < PES17_X86_BYTES ? db->x64_size : PES17_X86_BYTES;
        s->arm_bytes = db->native_size < PES17_ARM_BYTES ? db->native_size : PES17_ARM_BYTES;
        memcpy(s->x86, (const void *)db->x64_readaddr, s->x86_bytes);
        memcpy(s->arm, DynarecMapWritableAddress(db->block), s->arm_bytes);
        __atomic_store_n(&s->state, 2, __ATOMIC_RELEASE);
    }
}

void wine_nx_perf20_report(void)
{
    char line[300];
    snprintf(line, sizeof(line),
        "[PERF20] fusion=%d identity=%d seen=%u blocks=%u guards=%u merged=%u runs=%u flow_rejected=%u scope_rejected=%u",
        __atomic_load_n(&pes20_mode, __ATOMIC_ACQUIRE),
        __atomic_load_n(&pes17_identity, __ATOMIC_ACQUIRE),
        __atomic_load_n(&pes20_seen, __ATOMIC_RELAXED),
        __atomic_load_n(&pes20_blocks, __ATOMIC_RELAXED),
        __atomic_load_n(&pes20_guards, __ATOMIC_RELAXED),
        __atomic_load_n(&pes20_merged, __ATOMIC_RELAXED),
        __atomic_load_n(&pes20_runs, __ATOMIC_RELAXED),
        __atomic_load_n(&pes20_flow, __ATOMIC_RELAXED),
        __atomic_load_n(&pes20_scope, __ATOMIC_RELAXED));
    if (&wine_nx_runtime_trace) wine_nx_runtime_trace(line);
}
