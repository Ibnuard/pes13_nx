/* Secondary-core contention repair, after the upstream minimax proposal was
 * rejected. Requires thread_profile.h; no kernel calls or allocations here. */
#ifndef PES13_PERF23_BALANCE_H
#define PES13_PERF23_BALANCE_H

/* Move at most one substantial, movable thread. The destination must retain
 * at least 15% of a core more headroom even after moving this thread there.
 * A fixed / non-single-core affinity is never broadened or overridden. */
static int pes23_secondary_move(struct nx_balance_thread *threads, unsigned count,
                               unsigned cores, uint64_t *benefit)
{
    unsigned loads[NX_BALANCE_MAX_CORES] = {0};
    unsigned peak = 0, i, c, best = count, target = 0;
    uint64_t best_gain = 0;
    if (benefit) *benefit = 0;
    if (cores < 2 || cores > NX_BALANCE_MAX_CORES) return 0;
    for (i = 0; i < count; ++i) {
        threads[i].new_core = threads[i].core;
        if (threads[i].core < 0 || (unsigned)threads[i].core >= cores) continue;
        loads[threads[i].core] += threads[i].load;
    }
    for (c = 0; c < cores; ++c) if (loads[c] > peak) peak = loads[c];
    for (i = 0; i < count; ++i) {
        const struct nx_balance_thread *t = &threads[i];
        unsigned rest;
        if (t->fixed || t->core < 0 || (unsigned)t->core >= cores || t->load < 100) continue;
        rest = loads[t->core] - t->load;
        for (c = 0; c < cores; ++c) {
            uint64_t gain;
            if ((int)c == t->core || rest < loads[c] + 150 || loads[c] + t->load > peak) continue;
            /* Exact drop in sum(core_load^2), without counting blocked time. */
            gain = 2ull * t->load * (rest - loads[c]);
            if (gain > best_gain) { best_gain = gain; best = i; target = c; }
        }
    }
    if (best == count) return 0;
    threads[best].new_core = (int)target;
    if (benefit) *benefit = best_gain;
    return 1;
}
#endif
