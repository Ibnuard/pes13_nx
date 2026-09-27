// SPDX-License-Identifier: MIT
#include "horizon_host.h"

static_assert(sizeof(pes13_fex_host) == 96);
static_assert(offsetof(pes13_fex_host, allocate_code) == 16);

extern "C" uint64_t PES13FexCallHost(uintptr_t callback, uint64_t arg0, uint64_t arg1);

namespace {
pes13_fex_host Host {};
bool Ready {};
uintptr_t SpareCode {};
uint64_t SpareCodeSize {};
bool SpareAttempted {};
template<typename Callback>
uint64_t CallHost(Callback callback, uint64_t arg0, uint64_t arg1 = 0);

// JIT emission writes many short instructions into the same CodeMemory arena.
// Crossing the PE/native callback for every write also scans native mapping
// slots each time. Publish the matching RW alias once per allocation instead.
// Even sequence = stable, odd = writer owns this slot. A reader may be
// scanning an unrelated mapping while another thread retires/reuses it.
// Atomics on individual fields alone do not make that snapshot consistent.
struct CodeAlias { uintptr_t rx, rw; uint64_t size, sequence; };
CodeAlias CodeAliases[64] {};

bool ClaimAlias(CodeAlias &entry, uintptr_t expected_rx) {
    auto sequence = __atomic_load_n(&entry.sequence, __ATOMIC_ACQUIRE);
    if ((sequence & 1) || __atomic_load_n(&entry.rx, __ATOMIC_RELAXED) != expected_rx ||
        !__atomic_compare_exchange_n(&entry.sequence, &sequence, sequence + 1, false,
                                      __ATOMIC_ACQ_REL, __ATOMIC_RELAXED)) return false;
    if (__atomic_load_n(&entry.rx, __ATOMIC_RELAXED) == expected_rx) return true;
    __atomic_fetch_add(&entry.sequence, 1, __ATOMIC_RELEASE);
    return false;
}

void PublishCodeAlias(void *rx, uint64_t size) {
    if (!rx || !size || size > UINT64_MAX - 4095) return;
    size = (size + 4095) & ~uint64_t{4095}; // Match native CodeMemory rounding.
    void *rw = reinterpret_cast<void *>(CallHost(Host.write_alias,
        reinterpret_cast<uintptr_t>(rx), 1));
    if (!rw || rw == rx) return; // Native lookup remains the safe fallback.
    for (auto &entry : CodeAliases) {
        if (!ClaimAlias(entry, 0)) continue;
        __atomic_store_n(&entry.rw, reinterpret_cast<uintptr_t>(rw), __ATOMIC_RELAXED);
        __atomic_store_n(&entry.size, size, __ATOMIC_RELAXED);
        __atomic_store_n(&entry.rx, reinterpret_cast<uintptr_t>(rx), __ATOMIC_RELAXED);
        __atomic_fetch_add(&entry.sequence, 1, __ATOMIC_RELEASE);
        return;
    }
}

CodeAlias *RetireCodeAlias(void *address) {
    const uintptr_t target = reinterpret_cast<uintptr_t>(address);
    for (auto &entry : CodeAliases) {
        if (ClaimAlias(entry, target)) return &entry;
    }
    return nullptr;
}

// Returns 1 for a complete mapping, -1 for a boundary crossing, 0 on a miss.
int CachedAlias(const void *address, uint64_t length, void **result) {
    const uintptr_t target = reinterpret_cast<uintptr_t>(address);
    if (length > UINTPTR_MAX - target) return -1;
    for (const auto &entry : CodeAliases) {
        const uint64_t sequence = __atomic_load_n(&entry.sequence, __ATOMIC_ACQUIRE);
        if (sequence & 1) continue; // Never spin in an exception handler.
        const uintptr_t rx = __atomic_load_n(&entry.rx, __ATOMIC_RELAXED);
        const uint64_t size = __atomic_load_n(&entry.size, __ATOMIC_RELAXED);
        const uintptr_t rw = __atomic_load_n(&entry.rw, __ATOMIC_RELAXED);
        __atomic_thread_fence(__ATOMIC_ACQUIRE);
        if (__atomic_load_n(&entry.sequence, __ATOMIC_ACQUIRE) != sequence || !rx) continue;
        if (target >= rx && target - rx < size) {
            const uint64_t offset = target - rx;
            if (length > size - offset) return -1;
            *result = reinterpret_cast<void *>(rw + offset);
            return 1;
        }
        if (target >= rw && target - rw < size) {
            if (length > size - (target - rw)) return -1;
            *result = const_cast<void *>(address);
            return 1;
        }
    }
    return 0;
}

template<typename Callback>
uint64_t CallHost(Callback callback, uint64_t arg0, uint64_t arg1) {
    return PES13FexCallHost(reinterpret_cast<uintptr_t>(callback), arg0, arg1);
}

uintptr_t CurrentTeb() {
    uintptr_t teb;
    asm volatile("mov %0, x18" : "=r"(teb) : : "memory");
    return teb;
}

[[noreturn]] void Fail(const char *message) {
    if (Ready && Host.log) CallHost(Host.log, reinterpret_cast<uintptr_t>(message));
    __builtin_trap();
}

char *Text(char *out, const char *value) {
    while (*value) *out++ = *value++;
    return out;
}

char *Hex(char *out, uint64_t value) {
    out = Text(out, "0x");
    for (int shift = 60; shift >= 0; shift -= 4)
        *out++ = "0123456789abcdef"[(value >> shift) & 15];
    return out;
}
}

extern "C" int PES13FexSetHost(const pes13_fex_host *host) {
    if (Ready || !host || host->magic != PES13_FEX_HOST_MAGIC ||
        host->version != PES13_FEX_HOST_ABI || host->size != sizeof(Host) ||
        host->reserved || !host->allocate_code || !host->release_code ||
        !host->write_alias || !host->flush_code || !host->log ||
        !host->allocate_scratch || !host->release_scratch ||
        !host->allocate_heap || !host->release_heap || !host->performance_profile) return 0;
    Host = *host;
    Ready = true;
    PES13FexLog("[FEX-HOST] ABI 3 installed; native heap/scratch, dual mapping; x18 guarded");
    return 1;
}

extern "C" int PES13FexHostReady(void) { return Ready; }
extern "C" void PES13FexLog(const char *message) {
    if (Ready && message) CallHost(Host.log, reinterpret_cast<uintptr_t>(message));
}

extern "C" void *PES13FexAllocateScratch(uint64_t size) {
    if (!Ready) Fail("[FEX-HOST] missing host before scratch allocation");
    return reinterpret_cast<void *>(CallHost(Host.allocate_scratch, size));
}

extern "C" void PES13FexReleaseScratch(void *address) {
    if (!Ready) Fail("[FEX-HOST] missing host before scratch release");
    if (address) CallHost(Host.release_scratch, reinterpret_cast<uintptr_t>(address));
}

extern "C" void *PES13FexHeapAlloc(uint64_t size, uint64_t alignment) {
    if (!Ready) Fail("[FEX-HOST] missing host before heap allocation");
    return reinterpret_cast<void *>(CallHost(Host.allocate_heap, size, alignment));
}

extern "C" void PES13FexHeapFree(void *address) {
    if (!Ready) Fail("[FEX-HOST] missing host before heap release");
    if (address) CallHost(Host.release_heap, reinterpret_cast<uintptr_t>(address));
}

extern "C" unsigned PES13FexPerformanceProfile(void) {
    if (!Ready) Fail("[FEX-HOST] missing host before profile read");
    return static_cast<unsigned>(CallHost(Host.performance_profile, 0));
}

extern "C" void PES13FexHostPreflight(void) {
    const uintptr_t teb = CurrentTeb();
    if (!Ready || !teb) Fail("[FEX2-ABI] STOP missing host or Wine TEB");
    PES13FexLog("[FEX2-ABI] v4 checking PE/native callback preserves x18");
    if (CurrentTeb() != teb) Fail("[FEX2-ABI] STOP Wine TEB changed after host callback");
    PES13FexLog("[FEX2-ABI] PASS callback preserves Wine TEB");
}

extern "C" void *PES13FexTryAllocateCode(uint64_t size) {
    if (!Ready) Fail("[FEX-HOST] missing host before JIT allocation");
    if (__atomic_load_n(&SpareCode, __ATOMIC_ACQUIRE) && size == SpareCodeSize) {
        if (auto rx = __atomic_exchange_n(&SpareCode, 0, __ATOMIC_ACQ_REL)) {
            PES13FexLog("[FEX3-CODE] consuming early spare; no late mapping search");
            return reinterpret_cast<void *>(rx); // Alias was published at reserve time.
        }
    }
    void *rx = reinterpret_cast<void *>(CallHost(Host.allocate_code, size));
    if (rx) PublishCodeAlias(rx, size);
    return rx;
}

extern "C" void PES13FexPrimeCodeCache(uint64_t size) {
    if (!Ready || !PES13FexPerformanceProfile() ||
        __atomic_exchange_n(&SpareAttempted, true, __ATOMIC_ACQ_REL)) return;
    // A fresh, unexecuted buffer: never reset/free/reuse a cache still held by
    // any worker. Failure is optional; the normal growth/fallback remains.
    void *rx = reinterpret_cast<void *>(CallHost(Host.allocate_code, size));
    if (!rx) {
        PES13FexLog("[FEX3-CODE] early spare unavailable; ordinary growth retained");
        return;
    }
    PublishCodeAlias(rx, size);
    SpareCodeSize = size;
    __atomic_store_n(&SpareCode, reinterpret_cast<uintptr_t>(rx), __ATOMIC_RELEASE);
    PES13FexLog("[FEX3-CODE] early spare ready; one additional 128 MiB generation");
}

extern "C" void *PES13FexAllocateCode(uint64_t size) {
    void *result = PES13FexTryAllocateCode(size);
    if (!result) Fail("[FEX-HOST] executable allocation failed");
    return result;
}

extern "C" void PES13FexLogCodeFallback(uint64_t requested, uint64_t actual) {
    char message[112];
    char *out = Hex(Text(message, "[FEX3-CODE] fallback requested="), requested);
    out = Hex(Text(out, " actual="), actual);
    *out = 0;
    PES13FexLog(message);
}

extern "C" void PES13FexCodeFailure(const char *operation, uint64_t size) {
    char message[128];
    char *out = Text(Text(message, "[FEX3-CODE] STOP "), operation);
    out = Hex(Text(out, " bytes="), size);
    *out = 0;
    Fail(message);
}

extern "C" int PES13FexReleaseCode(void *rx) {
    if (!Ready) Fail("[FEX-HOST] missing host before JIT release");
    CodeAlias *entry = RetireCodeAlias(rx);
    int result = static_cast<int>(CallHost(Host.release_code, reinterpret_cast<uintptr_t>(rx)));
    if (entry) {
        __atomic_store_n(&entry->rx, result == 0 ? reinterpret_cast<uintptr_t>(rx) : 0,
                         __ATOMIC_RELAXED);
        __atomic_fetch_add(&entry->sequence, 1, __ATOMIC_RELEASE);
    }
    if (result < 0) Fail("[FEX-HOST] executable release failed");
    return result;
}

extern "C" void *PES13FexWriteAlias(const void *address, uint64_t size) {
    if (!Ready) Fail("[FEX-HOST] missing host before code write");
    void *result = nullptr;
    const int cached = CachedAlias(address, size, &result);
    if (cached < 0) Fail("[FEX-HOST] code write crossed allocation boundary");
    if (!cached) result = reinterpret_cast<void *>(CallHost(Host.write_alias,
                                                reinterpret_cast<uintptr_t>(address), size));
    if (!result && size) Fail("[FEX-HOST] code write crossed allocation boundary");
    return result;
}

extern "C" void PES13FexFlushCode(const void *address, uint64_t size) {
    if (!Ready || !static_cast<int>(CallHost(Host.flush_code, reinterpret_cast<uintptr_t>(address), size)))
        Fail("[FEX-HOST] invalid instruction-cache flush");
}
