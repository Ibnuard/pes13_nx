/* Called only while constructing the immutable, post-present game environment.
 * No global Box64 setting changes while guest threads are running. */
#ifndef PES13_PERF26_H
#define PES13_PERF26_H
static int pes26_mode;
static void pes26_configure(box64env_t *env)
{
    if (!pes26_mode) return;
    env->dynarec_callret = 2;
    env->is_dynarec_callret_overridden = 1;
    env->is_any_overridden = 1;
}
void wine_nx_perf26_report(void)
{
    char line[200];
    snprintf(line,sizeof(line),
        "[PERF26] guarded_callret=%d baseline_CALLRET=%d; game setting in PERF21; startup and DLLs unchanged",
        __atomic_load_n(&pes26_mode,__ATOMIC_ACQUIRE),box64env.dynarec_callret);
    if (&wine_nx_runtime_trace) wine_nx_runtime_trace(line);
}
#endif
