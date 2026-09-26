/* SPDX-License-Identifier: MIT
 * Versioned C ABI between the native Horizon host and the ARM64 PE FEX DLL.
 * Only integer/pointer arguments cross this boundary (AAPCS64 / Windows ARM64).
 * The host owns executable mappings. Their lifetime must outlive all users.
 */
#ifndef PES13_FEX_HORIZON_HOST_H
#define PES13_FEX_HORIZON_HOST_H
#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define PES13_FEX_HOST_ABI 3u
#define PES13_FEX_HOST_MAGIC 0x46455848u

enum pes13_fex_profile {
    PES13_FEX_CONTROL = 0,
    PES13_FEX_FAST = 1,
    PES13_FEX_FASTEST = 2,
    PES13_FEX_FAST_VECTOR = 3,
};

struct pes13_fex_host {
    uint32_t magic;
    uint32_t version;
    uint32_t size;
    uint32_t reserved;
    void *(*allocate_code)(uint64_t size);
    /* 1 = freed, 0 = not ours, -1 = error. Only the allocation base is valid. */
    int (*release_code)(void *rx);
    /* Identity for ordinary buffers; NULL for a range crossing a JIT boundary. */
    void *(*write_alias)(const void *address, uint64_t size);
    int (*flush_code)(const void *address, uint64_t size);
    void (*log)(const char *message);
    /* Native heap is outside Wine's 32-bit guest VM reservation. Only
     * unguarded compiler scratch uses this pair; JIT output uses CodeMemory. */
    void *(*allocate_scratch)(uint64_t size);
    void (*release_scratch)(void *address);
    /* FEX-private CRT/container allocations only. Never guest VirtualAlloc,
     * guarded mappings, executable code, or pointers freed by guest CRTs. */
    void *(*allocate_heap)(uint64_t size, uint64_t alignment);
    void (*release_heap)(void *address);
    unsigned (*performance_profile)(void); /* enum pes13_fex_profile */
};

/* Immediately before an allocate_heap result. Read-only to the PE module;
 * native release owns the original allocation. Shared across both ABIs. */
struct pes13_fex_heap_header { void *allocation; uint64_t size; };

/* Install once before BTCpuProcessInit; never changes a running instance. */
int PES13FexSetHost(const struct pes13_fex_host *host);
int PES13FexHostReady(void);
void *PES13FexAllocateCode(uint64_t size);
/* Shared caches may negotiate a smaller fresh buffer; fixed allocations stay strict. */
void *PES13FexTryAllocateCode(uint64_t size);
/* Optional one-generation reserve, acquired before 3D fragments guest VA. */
void PES13FexPrimeCodeCache(uint64_t size);
void PES13FexLogCodeFallback(uint64_t requested, uint64_t actual);
__attribute__((noreturn)) void PES13FexCodeFailure(const char *operation, uint64_t size);
int PES13FexReleaseCode(void *rx);
void *PES13FexWriteAlias(const void *address, uint64_t size);
void PES13FexFlushCode(const void *address, uint64_t size);
void PES13FexLog(const char *message);
void *PES13FexAllocateScratch(uint64_t size);
void PES13FexReleaseScratch(void *address);
void *PES13FexHeapAlloc(uint64_t size, uint64_t alignment);
void PES13FexHeapFree(void *address);
void *PES13FexHeapCalloc(size_t count, size_t size);
void *PES13FexHeapRealloc(void *address, size_t size);
size_t PES13FexHeapUsableSize(void *address);
int PES13FexHeapPosixAlign(void **result, size_t alignment, size_t size);
void PES13FexApplyPerformanceProfile(void);
unsigned PES13FexPerformanceProfile(void);
/* PE-side bring-up checks and failure diagnostics; safe before CRT startup. */
void PES13FexHostPreflight(void);
void PES13FexAllocationPreflight(void);
void PES13FexCounterPreflight(void);
/* Heap preflight runs after CRT; failure logging itself never allocates. */
void PES13FexHeapPreflight(void);
/* Reserve exact heap size with Wine-enforced alignment, without padding. */
void *PES13FexReserveHeap(uint64_t size, uint64_t alignment, uint32_t flags);
__attribute__((noreturn)) void PES13FexHeapFailure(const char *operation, uint64_t size);
void PES13FexLogAllocationFailure(const char *api, uint64_t address, uint64_t size,
                                  uint32_t type, uint32_t protect, uint32_t status);
void PES13FexLogSMCProtectFailure(uint64_t address, uint64_t size,
                                 uint32_t protect, uint32_t status);
/* Compile-time policy only: no helper calls in executed guest arithmetic. */
int PES13FexCanBatchSMC(uint64_t image, uint64_t image_size, const char *name,
                      uint64_t address, uint64_t size);
void PES13FexRecordSMC(uint64_t instructions, unsigned mode);
/* Commit a bounded part of an owned lazy data mapping after a read/write fault. */
int PES13FexCommitTrackedMemory(uint64_t fault, uint64_t range_start, uint64_t range_end);
/* Bounded guest-exception breadcrumbs; no heap or per-instruction logging. */
uint32_t PES13FexBeginGuestFaultTrace(uint64_t tid, uint64_t host_pc, uint64_t address);
void PES13FexTraceGuestFault(uint32_t ticket, const char *stage, uint64_t pc, uint64_t value);

/* Native implementation, also exercised by the standalone JIT probe. */
const struct pes13_fex_host *pes13_fex_native_host(void);
void pes13_fex_set_logger(void (*logger)(const char *));
/* Startup only: guest tests override every speed option; vector relaxation
 * is opt-in and applies only to Fast. Existing preset numbers stay stable. */
unsigned pes13_fex_select_performance_profile(int guest_tests, int fast,
                                              int fastest, int relaxed_vectors);
void pes13_fex_set_performance_profile(unsigned profile);
void pes13_fex_report_heap(void);

#ifdef __cplusplus
}

template<typename T> inline T *PES13FexWritable(T *address) {
    return static_cast<T *>(PES13FexWriteAlias(address, sizeof(T)));
}
#endif
#endif
