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
#include <string.h>
#include <limits.h>

_Static_assert(sizeof(struct pes13_fex_host) == 56, "FEX host ABI requires 64-bit pointers");
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

#define JIT_SLOTS 8
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
    if (!map) { HOST_UNLOCK(&allocation_lock); return NULL; }
#ifdef __SWITCH__
    Result rc = jitCreate(&map->jit, size);
    if (R_FAILED(rc)) {
        char message[128];
        snprintf(message, sizeof(message), "[FEX-JIT] jitCreate size=%zu rc=%#x", size, rc);
        host_log(message);
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

const struct pes13_fex_host *pes13_fex_native_host(void) {
    static const struct pes13_fex_host host = {
        PES13_FEX_HOST_MAGIC, PES13_FEX_HOST_ABI, sizeof(struct pes13_fex_host), 0,
        allocate_code, release_code, write_alias, flush_code, host_log
    };
    return &host;
}
