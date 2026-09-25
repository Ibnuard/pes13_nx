// SPDX-License-Identifier: MIT
#define NTDDI_VERSION 0x0A000005
#define WINAPI
#define WINBASEAPI
#include <windows.h>
#include <rpmalloc/rpmalloc.h>
#include "horizon_host.h"
#include "horizon_heap.h"

namespace {
// No printf, malloc, or C++ runtime: an allocation failure may precede CRT init.
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

[[noreturn]] void Stop(const char *message) {
    PES13FexLog(message);
    __builtin_trap();
}
}

extern "C" void PES13FexLogAllocationFailure(const char *api, uint64_t address, uint64_t size,
                                            uint32_t type, uint32_t protect, uint32_t status) {
    char message[240];
    char *out = Text(message, "[FEX2-ALLOC] FAIL ");
    // API names are internal fixed strings, not input from the guest.
    out = Text(out, api);
    out = Hex(Text(out, " base="), address);
    out = Hex(Text(out, " size="), size);
    out = Hex(Text(out, " type="), type);
    out = Hex(Text(out, " protect="), protect);
    out = Hex(Text(out, " status="), status);
    *out = 0;
    PES13FexLog(message);
}

extern "C" int PES13FexCommitTrackedMemory(uint64_t fault, uint64_t range_start, uint64_t range_end) {
    constexpr uint64_t page = 4096, chunk = 64 * 1024;
    // Do not commit from AllocationBase: Wine can return the whole untouched
    // reservation as one region. Only FEX's owned, aligned intervals belong
    // here; a failed null reservation must never claim guest address space.
    if (!range_start || range_end <= range_start || ((range_start | range_end) & (page-1)) ||
        fault < range_start || fault >= range_end) return 0;
    const uint64_t address = fault & ~(page-1);
    MEMORY_BASIC_INFORMATION info {};
    if (VirtualQuery(reinterpret_cast<void *>(address), &info, sizeof(info)) != sizeof(info)) return 0;
    const uint64_t region = reinterpret_cast<uintptr_t>(info.BaseAddress);
    if (region > address || info.RegionSize > UINT64_MAX - region ||
        region + info.RegionSize <= address) return 0;
    // Another thread can satisfy this fault before our query. Only ordinary
    // writable data pages are retryable; never swallow a guest protection fault.
    if (info.State == MEM_COMMIT)
        return !(info.Protect & (PAGE_GUARD | PAGE_NOACCESS)) &&
               (info.Protect & (PAGE_READWRITE | PAGE_WRITECOPY));
    if (info.State != MEM_RESERVE) return 0;
    uint64_t size = range_end - address;
    if (size > region + info.RegionSize - address) size = region + info.RegionSize - address;
    if (size > chunk) size = chunk;
    if (!size || (size & (page-1))) return 0;
    return VirtualAlloc(reinterpret_cast<void *>(address), size, MEM_COMMIT, PAGE_READWRITE) ==
           reinterpret_cast<void *>(address);
}

extern "C" void PES13FexAllocationPreflight(void) {
    PES13FexLog("[FEX2-ALLOC] v2 Wine-managed address limits; checking before CRT");
    constexpr SIZE_T size = 4096;
    void *allocation = VirtualAlloc(nullptr, size, MEM_RESERVE | MEM_TOP_DOWN, PAGE_READWRITE);
    if (!allocation) Stop("[FEX2-ALLOC] STOP reserve failed before CRT");
    if (VirtualAlloc(allocation, size, MEM_COMMIT, PAGE_READWRITE) != allocation)
        Stop("[FEX2-ALLOC] STOP commit failed before CRT");
    auto *bytes = static_cast<volatile unsigned char *>(allocation);
    bytes[0] = 0x5a;
    bytes[size - 1] = 0xa5;
    if (bytes[0] != 0x5a || bytes[size - 1] != 0xa5)
        Stop("[FEX2-ALLOC] STOP data readback failed before CRT");
    if (!VirtualFree(allocation, 0, MEM_RELEASE))
        Stop("[FEX2-ALLOC] STOP release failed before CRT");

    // Exercise the Ex path with the caller's alignment requirement intact.
    MEM_ADDRESS_REQUIREMENTS requirements {};
    requirements.Alignment = 0x10000;
    MEM_EXTENDED_PARAMETER parameter {};
    parameter.Type = MemExtendedParameterAddressRequirements;
    parameter.Pointer = &requirements;
    allocation = VirtualAlloc2(nullptr, nullptr, size, MEM_RESERVE | MEM_COMMIT,
                               PAGE_READWRITE, &parameter, 1);
    if (!allocation) Stop("[FEX2-ALLOC] STOP extended allocation failed before CRT");
    if (reinterpret_cast<uintptr_t>(allocation) & (requirements.Alignment - 1))
        Stop("[FEX2-ALLOC] STOP alignment mismatch before CRT");
    *static_cast<volatile unsigned char *>(allocation) = 0x3c;
    if (!VirtualFree(allocation, 0, MEM_RELEASE))
        Stop("[FEX2-ALLOC] STOP extended release failed before CRT");
    PES13FexLog("[FEX2-ALLOC] PASS reserve/commit/write/free and extended alignment");
}

extern "C" void PES13FexHeapFailure(const char *operation, uint64_t size) {
    char message[128];
    char *out = Text(message, "[FEX2-HEAP] STOP ");
    out = Text(out, operation); // Internal fixed strings only.
    out = Hex(Text(out, " failed bytes="), size);
    *out = 0;
    Stop(message);
}

extern "C" void *PES13FexReserveHeap(uint64_t size, uint64_t alignment, uint32_t flags) {
    // rpmalloc normally reserves size+alignment and keeps the padding until
    // release. Our 32-bit prefix cannot afford that extra span of padding.
    // Let Wine select an aligned address while holding its VM lock. Never
    // release/re-reserve a candidate: another thread could claim the gap.
    if (!alignment)
        return VirtualAlloc(nullptr, size, flags, PAGE_READWRITE);
    MEM_ADDRESS_REQUIREMENTS requirements {};
    requirements.Alignment = alignment;
    MEM_EXTENDED_PARAMETER parameter {};
    parameter.Type = MemExtendedParameterAddressRequirements;
    parameter.Pointer = &requirements;
    return VirtualAlloc2(nullptr, nullptr, size, flags, PAGE_READWRITE, &parameter, 1);
}

extern "C" void PES13FexHeapPreflight(void) {
    PES13FexLog("[FEX3-HEAP] v8 native private CRT/container heap; no guest spans");
    constexpr size_t sizes[] = {24, 8192, 1024 * 1024,
                               PES13_FEX_HEAP_LARGE_BLOCK_LIMIT,
                               PES13_FEX_HEAP_LARGE_BLOCK_LIMIT + 1};
    void *blocks[5] {};
    for (size_t i = 0; i < 5; ++i) {
        blocks[i] = PES13FexHeapAlloc(sizes[i], i == 4 ? 65536 : 16);
        if (!blocks[i]) PES13FexHeapFailure("allocation", sizes[i]);
        if (reinterpret_cast<uintptr_t>(blocks[i]) & (i == 4 ? 65535 : 15))
            Stop("[FEX3-HEAP] STOP native heap alignment mismatch");
        auto *bytes = static_cast<volatile unsigned char *>(blocks[i]);
        bytes[0] = 0x5a;
        bytes[sizes[i] - 1] = 0xa5;
        if (bytes[0] != 0x5a || bytes[sizes[i] - 1] != 0xa5)
            Stop("[FEX2-HEAP] STOP block readback failed");
    }
    for (void *block : blocks) PES13FexHeapFree(block);
    PES13FexLog("[FEX3-HEAP] PASS native small/large/aligned allocation, write and free");
}
