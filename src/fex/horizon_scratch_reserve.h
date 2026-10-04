/* SPDX-License-Identifier: MIT
 * One bounded contiguous scratch arena. Adjacent released units can satisfy a
 * larger compiler request; live allocations never move or lose ownership.
 * Host ABI and the frozen PE allocator/ownership protocol are unchanged.
 */
#ifndef PES13_HORIZON_SCRATCH_RESERVE_H
#define PES13_HORIZON_SCRATCH_RESERVE_H
#define FX_SCRATCH_UNIT (8u * 1024u * 1024u)
#ifndef FX_SCRATCH_UNITS
#define FX_SCRATCH_UNITS 4u
#endif
#if FX_SCRATCH_UNITS != 4u && FX_SCRATCH_UNITS != 8u
#error "Scratch reserve must be bounded to 32 or 64 MiB"
#endif
#define FX_SCRATCH_BYTES (FX_SCRATCH_UNIT * FX_SCRATCH_UNITS)
#if defined(FX_SCRATCH_PAGES) && defined(__SWITCH__)
#include "horizon_scratch_pages.h"
#endif
static unsigned char *fx_scratch_base;
static unsigned fx_scratch_units, fx_scratch_used;
/* Length is recorded only at the allocation start, never at interior units. */
static unsigned char fx_scratch_lengths[FX_SCRATCH_UNITS];
#ifdef __SWITCH__
static host_mutex fx_scratch_lock;
#else
static host_mutex fx_scratch_lock = PTHREAD_MUTEX_INITIALIZER;
#endif
static unsigned fx_scratch_init_started;
enum fx_scratch_metric {
    FX_SC_CAPACITY, FX_SC_USED, FX_SC_LIVE, FX_SC_HITS, FX_SC_FALLBACK,
    FX_SC_FAILED, FX_SC_PEAK_USED, FX_SC_RETURNED, FX_SC_INIT_FAILED,
    FX_SC_LARGEST_FREE, FX_SC_MAX_REQUEST, FX_SC_LAST_FAILED,
    FX_SC_HITS_8, FX_SC_HITS_16, FX_SC_HITS_LARGER, FX_SC_BAD_RELEASE,
    FX_SC_METRICS
};
static uint64_t fx_scratch_stats[FX_SC_METRICS];

static void fx_scratch_reserve_init(void) {
    if (__atomic_exchange_n(&fx_scratch_init_started, 1, __ATOMIC_ACQ_REL)) return;
    /* Before guest/DXVK workers. A smaller *contiguous* arena is still useful
     * if the full reserve is unavailable; never exceed the configured cap.
     * HIGH can hold 16+8+8 MiB while another compiler needs 8 MiB. The optional
     * 64-MiB cap covers that live overlap before the general heap fragments. */
    for (unsigned units = FX_SCRATCH_UNITS; units; units /= 2) {
        void *p = aligned_alloc(PAGE_BYTES, units * FX_SCRATCH_UNIT);
        HOST_LOCK(&fx_scratch_lock);
        if (p) {
            fx_scratch_base = p;
            fx_scratch_units = units;
            fx_scratch_stats[FX_SC_CAPACITY] = units * FX_SCRATCH_UNIT;
        } else {
            fx_scratch_stats[FX_SC_INIT_FAILED]++;
        }
        HOST_UNLOCK(&fx_scratch_lock);
        if (p) break;
    }
}

static void *fx_scratch_reserve_take(size_t size) {
    HOST_LOCK(&fx_scratch_lock);
    if (size > fx_scratch_stats[FX_SC_MAX_REQUEST])
        fx_scratch_stats[FX_SC_MAX_REQUEST] = size;
    /* Small/lookup allocations keep their ordinary allocation path. Round a
     * large workspace up to whole units without exposing a smaller buffer. */
    if (size >= FX_SCRATCH_UNIT && size <= FX_SCRATCH_BYTES) {
        unsigned units = (unsigned)((size + FX_SCRATCH_UNIT - 1) / FX_SCRATCH_UNIT);
        for (unsigned i = 0; i + units <= fx_scratch_units; i++) {
            unsigned mask = ((1u << units) - 1) << i;
            if (fx_scratch_used & mask) continue;
            fx_scratch_used |= mask;
            fx_scratch_lengths[i] = (unsigned char)units;
            fx_scratch_stats[FX_SC_USED] += units * FX_SCRATCH_UNIT;
            fx_scratch_stats[FX_SC_LIVE]++;
            fx_scratch_stats[FX_SC_HITS]++;
            fx_scratch_stats[units == 1 ? FX_SC_HITS_8 : units == 2 ? FX_SC_HITS_16 : FX_SC_HITS_LARGER]++;
            if (fx_scratch_stats[FX_SC_USED] > fx_scratch_stats[FX_SC_PEAK_USED])
                fx_scratch_stats[FX_SC_PEAK_USED] = fx_scratch_stats[FX_SC_USED];
            void *p = fx_scratch_base + i * FX_SCRATCH_UNIT;
            HOST_UNLOCK(&fx_scratch_lock);
            return p;
        }
    }
    fx_scratch_stats[FX_SC_FALLBACK]++;
    HOST_UNLOCK(&fx_scratch_lock);
    void *p = aligned_alloc(PAGE_BYTES, size);
#if defined(FX_SCRATCH_PAGES) && defined(__SWITCH__)
    if (!p) p = fx_scratch_pages_take(size);
#endif
    if (!p) {
        HOST_LOCK(&fx_scratch_lock);
        fx_scratch_stats[FX_SC_FAILED]++;
        fx_scratch_stats[FX_SC_LAST_FAILED] = size;
        HOST_UNLOCK(&fx_scratch_lock);
    }
    return p;
}

static void fx_scratch_reserve_release(void *address) {
    if (!address) return;
    HOST_LOCK(&fx_scratch_lock);
    uintptr_t offset = (uintptr_t)address - (uintptr_t)fx_scratch_base;
    if (fx_scratch_base && offset < fx_scratch_units * FX_SCRATCH_UNIT) {
        unsigned i = (unsigned)(offset / FX_SCRATCH_UNIT);
        unsigned units = fx_scratch_lengths[i];
        if (!(offset % FX_SCRATCH_UNIT) && units) {
            fx_scratch_used &= ~(((1u << units) - 1) << i);
            fx_scratch_lengths[i] = 0;
            fx_scratch_stats[FX_SC_USED] -= units * FX_SCRATCH_UNIT;
            fx_scratch_stats[FX_SC_LIVE]--;
            fx_scratch_stats[FX_SC_RETURNED]++;
        } else {
            /* Never pass an interior or already returned arena pointer to
             * libc free. Record the invalid caller without modifying owners. */
            fx_scratch_stats[FX_SC_BAD_RELEASE]++;
        }
        HOST_UNLOCK(&fx_scratch_lock);
        return;
    }
    HOST_UNLOCK(&fx_scratch_lock);
#if defined(FX_SCRATCH_PAGES) && defined(__SWITCH__)
    if (fx_scratch_pages_release(address)) return;
#endif
    free(address);
}

void pes13_fex_scratch_snapshot(uint64_t out[FX_SC_METRICS]) {
    HOST_LOCK(&fx_scratch_lock);
    unsigned run = 0, largest = 0;
    for (unsigned i = 0; i < fx_scratch_units; i++) {
        run = (fx_scratch_used & (1u << i)) ? 0 : run + 1;
        if (run > largest) largest = run;
    }
    fx_scratch_stats[FX_SC_LARGEST_FREE] = largest * FX_SCRATCH_UNIT;
    for (unsigned i = 0; i < FX_SC_METRICS; i++) out[i] = fx_scratch_stats[i];
    HOST_UNLOCK(&fx_scratch_lock);
}
#endif
