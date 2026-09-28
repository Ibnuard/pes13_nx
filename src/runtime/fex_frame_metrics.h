/* LGPL-2.1-or-later. Cumulative diagnostics only; never change guest time.
 * No allocation, sleep, mutex, or I/O on the presentation path. Snapshots
 * may straddle a concurrent update; totals are retained in the next report. */
#ifndef PES13_FEX_FRAME_METRICS_H
#define PES13_FEX_FRAME_METRICS_H
#include <stdint.h>

#define FEX_FRAME_BINS 9
static const uint64_t fex_frame_limits_us[FEX_FRAME_BINS - 1] = {
    8334, 16667, 20000, 33334, 50000, 100000, 250000, 500000
};
struct fex_frame_hist {
    uint64_t bins[FEX_FRAME_BINS], sum_us, peak_us;
};

static unsigned fex_frame_bucket(uint64_t us)
{
    unsigned i = 0;
    while (i < FEX_FRAME_BINS - 1 && us > fex_frame_limits_us[i]) ++i;
    return i;
}

static void fex_frame_add(struct fex_frame_hist *hist, uint64_t us)
{
    uint64_t peak = __atomic_load_n(&hist->peak_us, __ATOMIC_RELAXED);
    __atomic_add_fetch(&hist->bins[fex_frame_bucket(us)], 1, __ATOMIC_RELAXED);
    __atomic_add_fetch(&hist->sum_us, us, __ATOMIC_RELAXED);
    while (us > peak && !__atomic_compare_exchange_n(&hist->peak_us, &peak, us,
                                                   1, __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}
}

/* Peak is since launch, not a misleading reset/re-race maximum. */
static struct fex_frame_hist fex_frame_delta(const struct fex_frame_hist *hist,
                                            struct fex_frame_hist *previous)
{
    struct fex_frame_hist now, delta;
    unsigned i;
    for (i = 0; i < FEX_FRAME_BINS; ++i) {
        now.bins[i] = __atomic_load_n(&hist->bins[i], __ATOMIC_RELAXED);
        delta.bins[i] = now.bins[i] - previous->bins[i];
    }
    now.sum_us = __atomic_load_n(&hist->sum_us, __ATOMIC_RELAXED);
    delta.sum_us = now.sum_us - previous->sum_us;
    now.peak_us = delta.peak_us = __atomic_load_n(&hist->peak_us, __ATOMIC_RELAXED);
    *previous = now;
    return delta;
}
#endif
