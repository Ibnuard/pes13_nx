/* Included after PERF22. Selection/capture run under the translator mutex. */
#include "pes13_perf25_policy.h"
static int pes25_mode;
static unsigned int pes25_copy_checks, pes25_copy_accepted;

int wine_nx_perf25_copy(uintptr_t ip, const void *env)
{
    if (ip!=0x93df43) return 0;
    __atomic_add_fetch(&pes25_copy_checks,1,__ATOMIC_RELAXED);
    /* The environment was selected once at block entry after first present.
     * Its identity is stable across all four passes; do not re-read a live
     * present counter here and change instruction sizes between passes. */
    if (!pes25_mode || !pes17_check_image() ||
        (env != &pes21_env && env != &pes22_env)) return 0;
    if (!pes25_copy_match(ip,(const void *)(uintptr_t)0x93df30,sizeof(pes25_copy_guest),1,1,1)) return 0;
    __atomic_add_fetch(&pes25_copy_accepted,1,__ATOMIC_RELAXED);
    return 1;
}

void wine_nx_perf25_completed(void *opaque, const void *env)
{
    dynablock_t *db=opaque;
    uintptr_t guest=(uintptr_t)db->x64_addr;
    /* The build reserves slot 5 for the exact startup
     * fault instruction, including pre-present compilation, with no patch. */
    struct pes17_snapshot *s=&pes17_snapshots[5];
    if (pes17_capture && pes17_check_image() && db->is32bits && db->x64_size &&
        db->native_size && guest<=0x115c36f && 0x115c36f-guest<db->x64_size &&
        !__atomic_load_n(&s->state,__ATOMIC_ACQUIRE)) {
        __atomic_store_n(&s->state,1,__ATOMIC_RELAXED);
        s->region=5; s->bigblock=0; s->hash=db->hash;
        s->guest=guest; s->native=(uintptr_t)db->block;
        s->guest_size=db->x64_size; s->native_size=db->native_size;
        s->x86_bytes=db->x64_size<PES17_X86_BYTES ? db->x64_size:PES17_X86_BYTES;
        s->arm_bytes=db->native_size<PES17_ARM_BYTES ? db->native_size:PES17_ARM_BYTES;
        memcpy(s->x86,(const void *)db->x64_readaddr,s->x86_bytes);
        memcpy(s->arm,DynarecMapWritableAddress(db->block),s->arm_bytes);
        __atomic_store_n(&s->state,2,__ATOMIC_RELEASE);
    }
    wine_nx_perf22_completed(opaque,env);
}

void wine_nx_perf25_report(void)
{
    char line[240];
    snprintf(line,sizeof(line),"[PERF25] paircopy=%d compile_checks=%u accepted=%u site=0093df43 startup_capture=0115c36f slot=5; counts are translations, not executions",
        __atomic_load_n(&pes25_mode,__ATOMIC_ACQUIRE),
        __atomic_load_n(&pes25_copy_checks,__ATOMIC_RELAXED),
        __atomic_load_n(&pes25_copy_accepted,__ATOMIC_RELAXED));
    if (&wine_nx_runtime_trace) wine_nx_runtime_trace(line);
}
