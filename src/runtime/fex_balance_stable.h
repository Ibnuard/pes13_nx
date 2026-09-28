/* LGPL-2.1-or-later. Incremental placement, using the existing sampled loads.
 * Include after thread_profile.h. No kernel calls, allocation or guest IDs. */
#ifndef PES13_FEX_BALANCE_STABLE_H
#define PES13_FEX_BALANCE_STABLE_H

static inline unsigned fex_balance_stable(struct nx_balance_thread *threads,
                                         unsigned count, unsigned cores,
                                         unsigned *before)
{
    unsigned loads[NX_BALANCE_MAX_CORES] = {0};
    unsigned i, c, gain = 50, moved_load = ~0u, after = 0;
    int chosen = -1, target = -1;
    *before = 0;
    if (cores > NX_BALANCE_MAX_CORES) cores = NX_BALANCE_MAX_CORES;
    for (i = 0; i < count; ++i) {
        int valid = threads[i].core >= 0 && (unsigned)threads[i].core < cores;
        threads[i].new_core = valid ? threads[i].core : -1;
        if (valid) loads[threads[i].core] += threads[i].load;
    }
    for (c = 0; c < cores; ++c)
        if (loads[c] > *before) *before = loads[c];
    if (cores < 2) return *before;

    /* Recover one busy automatic worker outside the eligible single-core set.
     * Explicit guest affinity remains authoritative, including multi-core masks. */
    for (i = 0; i < count; ++i)
        if (!threads[i].fixed && threads[i].new_core < 0 &&
            threads[i].load >= 2 * NX_BALANCE_LIGHT &&
            (chosen < 0 || threads[i].load > threads[chosen].load)) chosen = (int)i;
    if (chosen >= 0) {
        target = 0;
        for (c = 1; c < cores; ++c) if (loads[c] < loads[target]) target = (int)c;
    } else {
        /* Keep the current layout. Find one move improving the affected pair's
         * peak by >5 percentage points. This also relieves a secondary core
         * when an unrelated fixed thread dominates the global maximum.
         * Equal benefit: move the lighter helper, preserve the hot worker. */
        for (i = 0; i < count; ++i) {
            const struct nx_balance_thread *t = &threads[i];
            if (t->fixed || t->new_core < 0 || t->load < NX_BALANCE_LIGHT) continue;
            for (c = 0; c < cores; ++c) {
                unsigned remaining, receiving, peak, improvement;
                if ((int)c == t->core || loads[t->core] <= loads[c]) continue;
                remaining = loads[t->core] - t->load;
                receiving = loads[c] + t->load;
                peak = remaining > receiving ? remaining : receiving;
                if (peak >= loads[t->core]) continue;
                improvement = loads[t->core] - peak;
                if (improvement > gain || (chosen >= 0 && improvement == gain && t->load < moved_load)) {
                    gain = improvement; moved_load = t->load;
                    chosen = (int)i; target = (int)c;
                }
            }
        }
    }
    if (chosen >= 0) {
        int from = threads[chosen].new_core;
        if (from >= 0) loads[from] -= threads[chosen].load;
        loads[target] += threads[chosen].load;
        threads[chosen].new_core = target;
    }
    for (c = 0; c < cores; ++c) if (loads[c] > after) after = loads[c];
    return after;
}

static inline int fex_balance_has_move(const struct nx_balance_thread *threads, unsigned count)
{
    for (unsigned i = 0; i < count; ++i)
        if (threads[i].new_core >= 0 && threads[i].new_core != threads[i].core) return 1;
    return 0;
}
#endif
