/* SPDX-License-Identifier: MIT
 * RX addresses stay canonical in FEX, including PC-relative branch math.
 * Only writes use the RW alias. No permission flip is performed per block.
 * Allocation/free require caller quiescence; lookup is lock-free so faults
 * and backpatch handlers do not recursively acquire an allocation lock.
 */
#define _GNU_SOURCE
#include "horizon_host.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>

_Static_assert(sizeof(struct pes13_fex_host) == 96, "FEX host ABI requires 64-bit pointers");
_Static_assert(offsetof(struct pes13_fex_host, allocate_code) == 16, "FEX host ABI layout");

#ifdef __SWITCH__
#include <switch.h>
typedef Mutex host_mutex;
#define HOST_LOCK(m) mutexLock(m)
#define HOST_UNLOCK(m) mutexUnlock(m)
#else
#include <pthread.h>
#include <sys/mman.h>
#include <unistd.h>
typedef pthread_mutex_t host_mutex;
#define HOST_LOCK(m) pthread_mutex_lock(m)
#define HOST_UNLOCK(m) pthread_mutex_unlock(m)
#endif

/* Small fallback buffers can keep several code generations alive while FEX
 * workers still hold references to older translated blocks. */
#define JIT_SLOTS 64
#define PAGE_BYTES 4096u

struct code_mapping {
    uintptr_t rx, rw;
    size_t size;
    uint64_t generation; /* odd = published, even = empty/changing */
    unsigned unusable; /* only accessed while allocation_lock is held */
#ifdef __SWITCH__
    Jit jit;
#endif
};
static struct code_mapping mappings[JIT_SLOTS];
#ifdef __SWITCH__
static host_mutex allocation_lock;
#else
static host_mutex allocation_lock = PTHREAD_MUTEX_INITIALIZER;
#endif
static void (*host_logger)(const char *);

void pes13_fex_set_logger(void (*logger)(const char *)) { host_logger = logger; }
static void host_log(const char *message) {
    if (host_logger) host_logger(message);
}

#ifdef __SWITCH__
/* libnx's jitCreate forwards a NULL result from virtmemFindCodeMemory to the
 * kernel, so an exhausted/fragmented alias range is reported only as an
 * ambiguous InvalidMemoryRange. Keep its CodeMemory ABI and backing allocator,
 * but distinguish each stage and never issue a mapping at address zero.
 * Successful objects remain compatible with jitClose. */
static Result create_code_memory(struct code_mapping *map, size_t size) {
    Jit *jit = &map->jit;
    const char *stage = "capabilities";
    Result rc = MAKERESULT(Module_Libnx, LibnxError_JitUnavailable);
    int owner_mapped = 0;
    char message[240];
    memset(jit, 0, sizeof(*jit));
    jit->type = JitType_CodeMemory;
    jit->size = size;
    if (!envIsSyscallHinted(0x4b) || !envIsSyscallHinted(0x4c)) goto fail;

    stage = "backing";
    jit->src_addr = aligned_alloc(PAGE_BYTES, size);
    if (!jit->src_addr) {
        rc = MAKERESULT(Module_Libnx, LibnxError_OutOfMemory);
        goto fail;
    }
    stage = "create";
    rc = svcCreateCodeMemory(&jit->handle, jit->src_addr, size);
    if (R_FAILED(rc)) goto fail;

    virtmemLock();
    stage = "find-rw";
    jit->rw_addr = virtmemFindCodeMemory(size, PAGE_BYTES);
    if (!jit->rw_addr) rc = MAKERESULT(Module_Kernel, KernelError_InvalidMemoryRange);
    else {
        stage = "map-rw";
        rc = svcControlCodeMemory(jit->handle, CodeMapOperation_MapOwner,
                                  jit->rw_addr, size, Perm_Rw);
    }
    virtmemUnlock();
    if (R_FAILED(rc)) goto fail;
    owner_mapped = 1;

    virtmemLock();
    stage = "find-rx";
    jit->rx_addr = virtmemFindCodeMemory(size, PAGE_BYTES);
    if (!jit->rx_addr) rc = MAKERESULT(Module_Kernel, KernelError_InvalidMemoryRange);
    else {
        stage = "map-rx";
        rc = svcControlCodeMemory(jit->handle, CodeMapOperation_MapSlave,
                                  jit->rx_addr, size, Perm_Rx);
    }
    virtmemUnlock();
    if (R_SUCCEEDED(rc)) return rc;

fail:
    snprintf(message, sizeof(message),
             "[FEX-JIT] allocation failed stage=%s size=%zu rc=%#x src=%p rw=%p rx=%p",
             stage, size, rc, jit->src_addr, jit->rw_addr, jit->rx_addr);
    host_log(message);
    if (owner_mapped) {
        Result cleanup = svcControlCodeMemory(jit->handle, CodeMapOperation_UnmapOwner,
                                               jit->rw_addr, size, Perm_None);
        if (R_FAILED(cleanup)) {
            map->unusable = 1;
            snprintf(message, sizeof(message),
                     "[FEX-JIT] cleanup failed stage=unmap-rw rc=%#x; retaining backing and slot", cleanup);
            host_log(message);
            return rc;
        }
    }
    if (jit->handle) {
        Result cleanup = svcCloseHandle(jit->handle);
        if (R_FAILED(cleanup)) {
            map->unusable = 1;
            snprintf(message, sizeof(message),
                     "[FEX-JIT] cleanup failed stage=close-handle rc=%#x; retaining backing and slot", cleanup);
            host_log(message);
            return rc;
        }
    }
    free(jit->src_addr);
    memset(jit, 0, sizeof(*jit));
    return rc;
}
#endif

/* 1 = wholly inside, -1 = overlaps but crosses, 0 = disjoint. */
static int range_overlap(uintptr_t address, uint64_t length, uintptr_t base, size_t size) {
    if (length > UINTPTR_MAX - address) return -1;
    if (address >= base && address - base < size)
        return length <= size - (address - base) ? 1 : -1;
    if (address < base && length > base - address) return -1;
    return 0;
}

struct mapping_view {
    struct code_mapping *map;
    uintptr_t rx, rw;
    size_t offset;
};

/* A slot can be retired/reused while an unrelated buffer is looked up. Read
 * atomic fields and validate their generation; do not spin in a fault handler.
 * An actual buffer user must retain its owner until the write/flush completes.
 */
static int find_mapping(const void *address, uint64_t length, struct mapping_view *view) {
    uintptr_t target = (uintptr_t)address;
    if (length > UINTPTR_MAX - target) return -1;
    for (unsigned i = 0; i < JIT_SLOTS; ++i) {
        struct code_mapping *map = &mappings[i];
        uint64_t generation = __atomic_load_n(&map->generation, __ATOMIC_ACQUIRE);
        if (!(generation & 1)) continue;
        size_t size = __atomic_load_n(&map->size, __ATOMIC_RELAXED);
        uintptr_t rx_base = __atomic_load_n(&map->rx, __ATOMIC_RELAXED);
        uintptr_t rw_base = __atomic_load_n(&map->rw, __ATOMIC_RELAXED);
        __atomic_thread_fence(__ATOMIC_ACQUIRE);
        if (__atomic_load_n(&map->generation, __ATOMIC_ACQUIRE) != generation) continue;
        int rx = range_overlap(target, length, rx_base, size);
        int rw = range_overlap(target, length, rw_base, size);
        if (rx < 0 || rw < 0) return -1;
        if (rx || rw) {
            *view = (struct mapping_view){ map, rx_base, rw_base, target - (rx ? rx_base : rw_base) };
            return 1;
        }
    }
    return 0;
}

static void *allocate_code(uint64_t requested) {
    if (!requested || requested > SIZE_MAX - (PAGE_BYTES - 1)) return NULL;
    size_t size = ((size_t)requested + PAGE_BYTES - 1) & ~(size_t)(PAGE_BYTES - 1);
    struct code_mapping *map = NULL;
    unsigned slot = 0;
    HOST_LOCK(&allocation_lock);
    for (; slot < JIT_SLOTS; ++slot) {
        if (!mappings[slot].unusable &&
            !(__atomic_load_n(&mappings[slot].generation, __ATOMIC_RELAXED) & 1)) {
            map = &mappings[slot]; break;
        }
    }
    if (!map) {
        unsigned active = 0, quarantined = 0;
        uint64_t live_bytes = 0;
        char message[176];
        for (unsigned i = 0; i < JIT_SLOTS; ++i) {
            quarantined += !!mappings[i].unusable;
            if (__atomic_load_n(&mappings[i].generation, __ATOMIC_RELAXED) & 1) {
                ++active;
                live_bytes += __atomic_load_n(&mappings[i].size, __ATOMIC_RELAXED);
            }
        }
        HOST_UNLOCK(&allocation_lock);
        snprintf(message, sizeof(message),
                 "[FEX-JIT] no free slots requested=%zu capacity=%u active=%u quarantined=%u live_bytes=%llu",
                 size, JIT_SLOTS, active, quarantined, (unsigned long long)live_bytes);
        host_log(message);
        return NULL;
    }
#ifdef __SWITCH__
    Result rc = create_code_memory(map, size);
    if (R_FAILED(rc)) {
        HOST_UNLOCK(&allocation_lock);
        return NULL;
    }
    if (map->jit.type != JitType_CodeMemory) {
        jitClose(&map->jit);
        host_log("[FEX-JIT] simultaneous RW/RX mappings unavailable");
        HOST_UNLOCK(&allocation_lock);
        return NULL;
    }
    uintptr_t rw_addr = (uintptr_t)jitGetRwAddr(&map->jit);
    uintptr_t rx_addr = (uintptr_t)jitGetRxAddr(&map->jit);
    if (!rw_addr || !rx_addr || rw_addr == rx_addr) {
        if (R_FAILED(jitClose(&map->jit))) map->unusable = 1;
        host_log("[FEX-JIT] invalid RW/RX aliases");
        HOST_UNLOCK(&allocation_lock);
        return NULL;
    }
#else
    int fd = memfd_create("pes13-fex-jit", 0);
    if (fd < 0) { HOST_UNLOCK(&allocation_lock); return NULL; }
    void *rw = MAP_FAILED, *rx = MAP_FAILED;
    if (!ftruncate(fd, size)) {
        rw = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
        rx = mmap(NULL, size, PROT_READ | PROT_EXEC, MAP_SHARED, fd, 0);
    }
    close(fd);
    if (rw == MAP_FAILED || rx == MAP_FAILED) {
        if (rw != MAP_FAILED) munmap(rw, size);
        if (rx != MAP_FAILED) munmap(rx, size);
        HOST_UNLOCK(&allocation_lock);
        return NULL;
    }
    uintptr_t rw_addr = (uintptr_t)rw;
    uintptr_t rx_addr = (uintptr_t)rx;
#endif
    __atomic_store_n(&map->rw, rw_addr, __ATOMIC_RELAXED);
    __atomic_store_n(&map->rx, rx_addr, __ATOMIC_RELAXED);
    __atomic_store_n(&map->size, size, __ATOMIC_RELAXED);
    __atomic_fetch_add(&map->generation, 1, __ATOMIC_RELEASE);
    void *result = (void *)rx_addr;
    HOST_UNLOCK(&allocation_lock);
    char message[160];
    snprintf(message, sizeof(message), "[FEX-JIT] slot=%u size=%zu rw=%p rx=%p",
             slot, size, (void *)rw_addr, result);
    host_log(message);
    return result;
}

static void *write_alias(const void *address, uint64_t size) {
    struct mapping_view view;
    int found = find_mapping(address, size, &view);
    if (found < 0) return NULL;
    return found ? (void *)(view.rw + view.offset) : (void *)address;
}

static int flush_code(const void *address, uint64_t size) {
    struct mapping_view view;
    int found = find_mapping(address, size, &view);
    if (found < 0 || (!address && size)) return 0;
    if (!size) return 1;
    void *rw = found ? (void *)(view.rw + view.offset) : (void *)address;
    void *rx = found ? (void *)(view.rx + view.offset) : (void *)address;
#ifdef __SWITCH__
    armDCacheClean(rw, size);
    armICacheInvalidate(rx, size);
#else
    __builtin___clear_cache((char *)rw, (char *)rw + size);
    __builtin___clear_cache((char *)rx, (char *)rx + size);
#endif
    return 1;
}

static int release_code(void *address) {
    struct mapping_view view;
    HOST_LOCK(&allocation_lock);
    int found = find_mapping(address, 1, &view);
    if (found <= 0) { HOST_UNLOCK(&allocation_lock); return found; }
    if (view.offset || (uintptr_t)address != view.rx) { HOST_UNLOCK(&allocation_lock); return -1; }
    struct code_mapping *map = view.map;
    __atomic_fetch_add(&map->generation, 1, __ATOMIC_ACQ_REL);
#ifdef __SWITCH__
    Result rc = jitClose(&map->jit);
    if (R_FAILED(rc)) {
        /* A failed close may have partially unmapped the object. Do not
         * republish it or reuse the slot with uncertain ownership. */
        map->unusable = 1;
        HOST_UNLOCK(&allocation_lock);
        return -1;
    }
#else
    size_t size = __atomic_load_n(&map->size, __ATOMIC_RELAXED);
    munmap((void *)view.rw, size);
    munmap((void *)view.rx, size);
#endif
    HOST_UNLOCK(&allocation_lock);
    return 1;
}

static void *allocate_scratch(uint64_t requested) {
    if (!requested || requested > SIZE_MAX - (PAGE_BYTES - 1)) return NULL;
    size_t size = ((size_t)requested + PAGE_BYTES - 1) & ~(size_t)(PAGE_BYTES - 1);
    void *result = aligned_alloc(PAGE_BYTES, size);
    if (requested >= 8 * 1024 * 1024) {
        static unsigned reported;
        unsigned ticket = __atomic_fetch_add(&reported, 1, __ATOMIC_RELAXED);
        if (ticket < 8 || !result) {
            char message[160];
            snprintf(message, sizeof(message), "[FEX3-SCRATCH] native size=%zu ptr=%p", size, result);
            host_log(message);
        }
    }
    return result;
}

static void release_scratch(void *address) { free(address); }

static uint64_t heap_live, heap_peak, heap_allocations, heap_failures;
static unsigned performance_profile;

void pes13_fex_set_performance_profile(unsigned profile) {
    performance_profile = profile <= 2 ? profile : 0; /* Before CPU/worker init. */
}
static unsigned get_performance_profile(void) { return performance_profile; }

static void *allocate_heap(uint64_t requested, uint64_t alignment) {
    /* FEX's private allocations have no guest page protection/alias needs.
     * Use one native allocation instead of reserving rpmalloc spans and
     * mapping a second low-4-GiB view for every committed page. */
    const size_t header_size = sizeof(struct pes13_fex_heap_header);
    if (!alignment) alignment = 16;
    if (alignment & (alignment - 1)) return NULL;
    if (alignment < 16) alignment = 16;
    uint64_t size = requested ? requested : 1;
    if (alignment > SIZE_MAX - header_size || size > SIZE_MAX - header_size - (alignment - 1))
        return NULL;
    void *raw = malloc((size_t)size + header_size + (size_t)alignment - 1);
    if (!raw) {
        uint64_t failures = __atomic_add_fetch(&heap_failures, 1, __ATOMIC_RELAXED);
        if (failures <= 8) {
            char message[128];
            snprintf(message, sizeof(message), "[FEX3-NHEAP] allocation failed bytes=%llu align=%llu",
                     (unsigned long long)size, (unsigned long long)alignment);
            host_log(message);
        }
        return NULL;
    }
    uintptr_t address = ((uintptr_t)raw + header_size + alignment - 1) & ~(uintptr_t)(alignment - 1);
    struct pes13_fex_heap_header *header = (struct pes13_fex_heap_header *)address - 1;
    header->allocation = raw;
    header->size = size;
    uint64_t live = __atomic_add_fetch(&heap_live, size, __ATOMIC_RELAXED);
    uint64_t peak = __atomic_load_n(&heap_peak, __ATOMIC_RELAXED);
    while (live > peak && !__atomic_compare_exchange_n(&heap_peak, &peak, live, 1,
                                                       __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}
    __atomic_add_fetch(&heap_allocations, 1, __ATOMIC_RELAXED);
    return (void *)address;
}

static void release_heap(void *address) {
    if (!address) return;
    struct pes13_fex_heap_header *header = (struct pes13_fex_heap_header *)address - 1;
    __atomic_sub_fetch(&heap_live, header->size, __ATOMIC_RELAXED);
    free(header->allocation);
}

void pes13_fex_report_heap(void) {
    char message[192];
    snprintf(message, sizeof(message), "[FEX3-NHEAP] live_kb=%llu peak_kb=%llu allocs=%llu failures=%llu",
             (unsigned long long)(__atomic_load_n(&heap_live, __ATOMIC_RELAXED) / 1024),
             (unsigned long long)(__atomic_load_n(&heap_peak, __ATOMIC_RELAXED) / 1024),
             (unsigned long long)__atomic_load_n(&heap_allocations, __ATOMIC_RELAXED),
             (unsigned long long)__atomic_load_n(&heap_failures, __ATOMIC_RELAXED));
    host_log(message);
}

const struct pes13_fex_host *pes13_fex_native_host(void) {
    static const struct pes13_fex_host host = {
        PES13_FEX_HOST_MAGIC, PES13_FEX_HOST_ABI, sizeof(struct pes13_fex_host), 0,
        allocate_code, release_code, write_alias, flush_code, host_log,
        allocate_scratch, release_scratch, allocate_heap, release_heap, get_performance_profile
    };
    return &host;
}
