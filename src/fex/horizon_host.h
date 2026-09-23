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

#define PES13_FEX_HOST_ABI 1u
#define PES13_FEX_HOST_MAGIC 0x46455848u

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
};

/* Install once before BTCpuProcessInit; never changes a running instance. */
int PES13FexSetHost(const struct pes13_fex_host *host);
int PES13FexHostReady(void);
void *PES13FexAllocateCode(uint64_t size);
int PES13FexReleaseCode(void *rx);
void *PES13FexWriteAlias(const void *address, uint64_t size);
void PES13FexFlushCode(const void *address, uint64_t size);
void PES13FexLog(const char *message);
/* PE-side bring-up checks and failure diagnostics; safe before CRT startup. */
void PES13FexHostPreflight(void);
void PES13FexAllocationPreflight(void);
void PES13FexCounterPreflight(void);
/* Heap preflight runs after CRT; failure logging itself never allocates. */
void PES13FexHeapPreflight(void);
__attribute__((noreturn)) void PES13FexHeapFailure(const char *operation, uint64_t size);
void PES13FexLogAllocationFailure(const char *api, uint64_t address, uint64_t size,
                                  uint32_t type, uint32_t protect, uint32_t status);

/* Native implementation, also exercised by the standalone JIT probe. */
const struct pes13_fex_host *pes13_fex_native_host(void);
void pes13_fex_set_logger(void (*logger)(const char *));

#ifdef __cplusplus
}

template<typename T> inline T *PES13FexWritable(T *address) {
    return static_cast<T *>(PES13FexWriteAlias(address, sizeof(T)));
}
#endif
#endif
