/* Bounded present diagnostics. No allocation, lock or I/O on the frame path. */
#ifndef PES13_PERF24_METRICS_H
#define PES13_PERF24_METRICS_H
#include <stdint.h>

#define PES24_BUCKETS 10
static const uint64_t pes24_limits_us[PES24_BUCKETS-1] = {
    16667, 33334, 50000, 66667, 100000, 200000, 500000, 1000000, 2000000
};
struct pes24_hist {
    uint64_t count[PES24_BUCKETS], total_us, maximum_us;
};
struct pes24_snapshot {
    uint64_t count[PES24_BUCKETS], total_us, maximum_us;
};

static inline unsigned pes24_bucket(uint64_t us)
{
    unsigned i = 0;
    while (i < PES24_BUCKETS-1 && us > pes24_limits_us[i]) ++i;
    return i;
}

static inline void pes24_add(struct pes24_hist *h, uint64_t us)
{
    uint64_t peak = __atomic_load_n(&h->maximum_us, __ATOMIC_RELAXED);
    __atomic_add_fetch(&h->count[pes24_bucket(us)], 1, __ATOMIC_RELAXED);
    __atomic_add_fetch(&h->total_us, us, __ATOMIC_RELAXED);
    while (peak < us && !__atomic_compare_exchange_n(&h->maximum_us, &peak, us,
                1, __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}
}

/* Approximate interval boundaries: concurrent increments may be assigned to
 * adjacent reports. Monotonic counters preserve totals; max is since launch. */
static inline struct pes24_snapshot pes24_delta(const struct pes24_hist *h,
                                               struct pes24_snapshot *previous)
{
    struct pes24_snapshot now, delta;
    for (unsigned i=0; i<PES24_BUCKETS; ++i) {
        now.count[i] = __atomic_load_n(&h->count[i], __ATOMIC_RELAXED);
        delta.count[i] = now.count[i] - previous->count[i];
    }
    now.total_us = __atomic_load_n(&h->total_us, __ATOMIC_RELAXED);
    now.maximum_us = __atomic_load_n(&h->maximum_us, __ATOMIC_RELAXED);
    delta.total_us = now.total_us - previous->total_us;
    delta.maximum_us = now.maximum_us;
    *previous = now;
    return delta;
}

/* Sample 2 seconds per 10-second wall-clock cycle at 20 ms cadence. */
static inline int pes24_sample_window(uint64_t elapsed_ns)
{
    return elapsed_ns % 10000000000ull >= 8000000000ull;
}
#endif
