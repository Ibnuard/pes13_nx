/* SPDX-License-Identifier: MIT
 * One bounded contiguous scratch arena. Compiler workspaces still consume
 * whole 8-MiB units. Only after ordinary/fragmented allocation fails may CPU
 * data borrow idle pages. Live allocations never move or lose ownership.
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
static void *fx_scratch_reserve_try(size_t,int);
static int fx_scratch_reserve_return(void *);
static int fx_scratch_reserve_contains(const void *);
#if defined(FX_SCRATCH_PAGES) && defined(__SWITCH__)
#define FX_SHARED_CPU_RECOVERY 1
/* The Wine pool callback uses trylock and releases only completely idle
 * arenas. No allocator lock is held while calling it. */
extern size_t wine_nx_release_idle_backing_pages(void) __attribute__((weak));
static size_t fx_heap_pressure_trim(void) {
    return wine_nx_release_idle_backing_pages?wine_nx_release_idle_backing_pages():0;
}
static void fx_heap_pressure_report(const char *,size_t,size_t,unsigned,unsigned,size_t,int);
#include "horizon_scratch_pages.h"
#endif
static unsigned char *fx_scratch_base;
static unsigned fx_scratch_units;
#define FX_SCRATCH_PAGES_PER_UNIT (FX_SCRATCH_UNIT / PAGE_BYTES)
#define FX_SCRATCH_PAGE_COUNT (FX_SCRATCH_BYTES / PAGE_BYTES)
#define FX_SCRATCH_INTERIOR UINT16_MAX
/* 32 KiB of metadata at the 64-MiB cap. Zero=free, length at the start,
 * UINT16_MAX=interior. No allocation is needed to recover an allocation. */
static uint16_t fx_scratch_lengths[FX_SCRATCH_PAGE_COUNT];
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
/* Cumulative pressure borrowing; live bytes remain in FX_SC_USED. */
static uint64_t fx_scratch_borrow_bytes, fx_scratch_borrow_hits;

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

/* Caller chooses the granularity; do not allocate from another pool here. */
static void *fx_scratch_reserve_try(size_t size, int borrowing) {
    if (!size || size > FX_SCRATCH_BYTES) return NULL;
    unsigned granularity = borrowing ? 1u : FX_SCRATCH_PAGES_PER_UNIT;
    unsigned pages = (unsigned)((size + PAGE_BYTES - 1) / PAGE_BYTES);
    pages = (pages + granularity - 1) / granularity * granularity;
    HOST_LOCK(&fx_scratch_lock);
    unsigned capacity = fx_scratch_units * FX_SCRATCH_PAGES_PER_UNIT;
    for (unsigned i = 0; i + pages <= capacity;) {
        unsigned free_pages = 0;
        while (free_pages < pages && !fx_scratch_lengths[i + free_pages]) free_pages++;
        if (free_pages == pages) {
            fx_scratch_lengths[i] = (uint16_t)pages;
            for (unsigned j = 1; j < pages; j++) fx_scratch_lengths[i + j] = FX_SCRATCH_INTERIOR;
            fx_scratch_stats[FX_SC_USED] += pages * PAGE_BYTES;
            fx_scratch_stats[FX_SC_LIVE]++;
            fx_scratch_stats[FX_SC_HITS]++;
            if (borrowing) { fx_scratch_borrow_bytes += pages * PAGE_BYTES; fx_scratch_borrow_hits++; }
            else fx_scratch_stats[pages == FX_SCRATCH_PAGES_PER_UNIT ? FX_SC_HITS_8 :
                                  pages == 2 * FX_SCRATCH_PAGES_PER_UNIT ? FX_SC_HITS_16 : FX_SC_HITS_LARGER]++;
            if (fx_scratch_stats[FX_SC_USED] > fx_scratch_stats[FX_SC_PEAK_USED])
                fx_scratch_stats[FX_SC_PEAK_USED] = fx_scratch_stats[FX_SC_USED];
            void *p = fx_scratch_base + i * PAGE_BYTES;
            HOST_UNLOCK(&fx_scratch_lock);
            return p;
        }
        /* Skip the occupied page; rounding preserves compiler alignment. */
        unsigned occupied = fx_scratch_lengths[i + free_pages];
        unsigned skip = occupied == FX_SCRATCH_INTERIOR ? 1 : occupied;
        i = (i + free_pages + skip + granularity - 1) / granularity * granularity;
    }
    HOST_UNLOCK(&fx_scratch_lock);
    return NULL;
}

static void *fx_scratch_reserve_take(size_t size) {
    HOST_LOCK(&fx_scratch_lock);
    if (size > fx_scratch_stats[FX_SC_MAX_REQUEST]) fx_scratch_stats[FX_SC_MAX_REQUEST] = size;
    HOST_UNLOCK(&fx_scratch_lock);
    void *p = size >= FX_SCRATCH_UNIT ? fx_scratch_reserve_try(size, 0) : NULL;
    if (p) return p;
    HOST_LOCK(&fx_scratch_lock);
    fx_scratch_stats[FX_SC_FALLBACK]++;
    HOST_UNLOCK(&fx_scratch_lock);
    p = aligned_alloc(PAGE_BYTES, size);
#if defined(FX_SCRATCH_PAGES) && defined(__SWITCH__)
    size_t trimmed=0;
    struct fx_sp_failure failure={FX_SP_OK,0};
    int pressure=!p;
    if(!p){trimmed=fx_heap_pressure_trim();if(trimmed)p=aligned_alloc(PAGE_BYTES,size);}
    if (!p) p = fx_scratch_pages_take_report(size,&failure);
#endif
    /* Small lookup tables and non-unit tails can use idle pages under
     * pressure without reserving another physical arena or mapping aliases. */
    if (!p) p = fx_scratch_reserve_try(size, 1);
#if defined(FX_SCRATCH_PAGES) && defined(__SWITCH__)
    if(pressure)fx_heap_pressure_report("scratch",size,PAGE_BYTES,failure.stage,failure.result,trimmed,p!=NULL);
#endif
    if (!p) {
        HOST_LOCK(&fx_scratch_lock);
        fx_scratch_stats[FX_SC_FAILED]++;
        fx_scratch_stats[FX_SC_LAST_FAILED] = size;
        HOST_UNLOCK(&fx_scratch_lock);
    }
    return p;
}

static int fx_scratch_reserve_contains(const void *address) {
    return fx_scratch_base && (uintptr_t)address-(uintptr_t)fx_scratch_base < fx_scratch_units*FX_SCRATCH_UNIT;
}

static int fx_scratch_reserve_return(void *address) {
    if (!address) return 0;
    uintptr_t offset = (uintptr_t)address - (uintptr_t)fx_scratch_base;
    /* The base/capacity are immutable after pre-worker initialization. */
    if (!fx_scratch_base || offset >= fx_scratch_units * FX_SCRATCH_UNIT) return 0;
    HOST_LOCK(&fx_scratch_lock);
    if (fx_scratch_base && offset < fx_scratch_units * FX_SCRATCH_UNIT) {
        unsigned i = (unsigned)(offset / PAGE_BYTES);
        unsigned pages = fx_scratch_lengths[i];
        if (!(offset % PAGE_BYTES) && pages && pages != FX_SCRATCH_INTERIOR) {
            for (unsigned j = 0; j < pages; j++) fx_scratch_lengths[i + j] = 0;
            fx_scratch_stats[FX_SC_USED] -= pages * PAGE_BYTES;
            fx_scratch_stats[FX_SC_LIVE]--;
            fx_scratch_stats[FX_SC_RETURNED]++;
        } else {
            /* Never pass an interior or already returned arena pointer to
             * libc free. Record the invalid caller without modifying owners. */
            fx_scratch_stats[FX_SC_BAD_RELEASE]++;
        }
        HOST_UNLOCK(&fx_scratch_lock);
        return 1;
    }
    HOST_UNLOCK(&fx_scratch_lock);
    return 0;
}

static void fx_scratch_reserve_release(void *address) {
    if (!address || fx_scratch_reserve_return(address)) return;
#if defined(FX_SCRATCH_PAGES) && defined(__SWITCH__)
    if (fx_scratch_pages_release(address)) return;
#endif
    free(address);
}

void pes13_fex_scratch_snapshot(uint64_t out[FX_SC_METRICS]) {
    HOST_LOCK(&fx_scratch_lock);
    unsigned run = 0, largest = 0;
    for (unsigned i = 0; i < fx_scratch_units * FX_SCRATCH_PAGES_PER_UNIT; i++) {
        run = fx_scratch_lengths[i] ? 0 : run + 1;
        if (run > largest) largest = run;
    }
    fx_scratch_stats[FX_SC_LARGEST_FREE] = largest * PAGE_BYTES;
    for (unsigned i = 0; i < FX_SC_METRICS; i++) out[i] = fx_scratch_stats[i];
    HOST_UNLOCK(&fx_scratch_lock);
}
#endif
