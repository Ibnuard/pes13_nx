/* Included in the bridge after PERF17/PERF19 and before the PERF20 wrapper.
 * Runs only at compilation, before cache publication; never on each frame. */
#include "pes13_perf38_fuse.h"
static int pes38_mode;
static unsigned int pes38_seen, pes38_blocks, pes38_guards, pes38_merged, pes38_flow;
static unsigned int pes38_hot_seen[2], pes38_hot_merged[2], pes38_hot_flow[2];

static struct pes20_result pes38_select_fusion(dynablock_t *db)
{
    uintptr_t guest=(uintptr_t)db->x64_addr;
    struct pes20_result r;
    unsigned int i;
    /* Identity, 32-bit, size, sep/callret and matrix exclusions are already
     * enforced by the unchanged PERF20 wrapper. Only measured math pages
     * receive the new pass. Everything else keeps the old one. */
    if (!pes38_mode || guest<0x112f000 || guest>=0x1131000 ||
        db->x64_size>0x1131000-guest)
        return pes20_fuse(db->block,db->native_size);
    r=pes38_fuse(db->block,db->native_size);
    __atomic_add_fetch(&pes38_seen,1,__ATOMIC_RELAXED);
    __atomic_add_fetch(&pes38_blocks,!!r.merged,__ATOMIC_RELAXED);
    __atomic_add_fetch(&pes38_guards,r.guards,__ATOMIC_RELAXED);
    __atomic_add_fetch(&pes38_merged,r.merged,__ATOMIC_RELAXED);
    __atomic_add_fetch(&pes38_flow,r.flow_rejected,__ATOMIC_RELAXED);
    for(i=0;i<2;++i) if(guest==(i ? 0x112f8f0u : 0x113027bu)) {
        __atomic_add_fetch(&pes38_hot_seen[i],1,__ATOMIC_RELAXED);
        __atomic_add_fetch(&pes38_hot_merged[i],r.merged,__ATOMIC_RELAXED);
        __atomic_add_fetch(&pes38_hot_flow[i],r.flow_rejected,__ATOMIC_RELAXED);
    }
    return r;
}

void wine_nx_perf38_report(void)
{
    char line[384];
    snprintf(line,sizeof line,
        "[PERF38] region_fusion=%d scope=112f000-1131000 seen=%u blocks=%u guards=%u merged=%u flow_rejected=%u hot113027b=%u/%u/%u hot112f8f0=%u/%u/%u (compiled/merged/rejected; not executions)",
        pes38_mode,
        __atomic_load_n(&pes38_seen,__ATOMIC_RELAXED),
        __atomic_load_n(&pes38_blocks,__ATOMIC_RELAXED),
        __atomic_load_n(&pes38_guards,__ATOMIC_RELAXED),
        __atomic_load_n(&pes38_merged,__ATOMIC_RELAXED),
        __atomic_load_n(&pes38_flow,__ATOMIC_RELAXED),
        __atomic_load_n(&pes38_hot_seen[0],__ATOMIC_RELAXED),
        __atomic_load_n(&pes38_hot_merged[0],__ATOMIC_RELAXED),
        __atomic_load_n(&pes38_hot_flow[0],__ATOMIC_RELAXED),
        __atomic_load_n(&pes38_hot_seen[1],__ATOMIC_RELAXED),
        __atomic_load_n(&pes38_hot_merged[1],__ATOMIC_RELAXED),
        __atomic_load_n(&pes38_hot_flow[1],__ATOMIC_RELAXED));
    if (&wine_nx_runtime_trace) wine_nx_runtime_trace(line);
}
