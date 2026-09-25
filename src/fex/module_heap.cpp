// SPDX-License-Identifier: MIT
#include "horizon_host.h"
#include <cstring>
#include <cerrno>

extern "C" size_t PES13FexHeapUsableSize(void *address) {
    return address ? (static_cast<pes13_fex_heap_header *>(address) - 1)->size : 0;
}

extern "C" void *PES13FexHeapCalloc(size_t count, size_t size) {
    if (size && count > SIZE_MAX / size) return nullptr;
    const size_t bytes = count * size;
    void *result = PES13FexHeapAlloc(bytes, 16);
    if (result) std::memset(result, 0, bytes);
    return result;
}

extern "C" void *PES13FexHeapRealloc(void *address, size_t size) {
    if (!address) return PES13FexHeapAlloc(size, 16);
    if (!size) { PES13FexHeapFree(address); return nullptr; }
    void *result = PES13FexHeapAlloc(size, 16);
    if (!result) return nullptr; // Preserve the original allocation on failure.
    size_t previous = PES13FexHeapUsableSize(address);
    std::memcpy(result, address, previous < size ? previous : size);
    PES13FexHeapFree(address);
    return result;
}

extern "C" int PES13FexHeapPosixAlign(void **result, size_t alignment, size_t size) {
    if (!result || alignment < sizeof(void *) || (alignment & (alignment - 1))) return EINVAL;
    void *address = PES13FexHeapAlloc(size, alignment);
    if (!address) return ENOMEM; // POSIX leaves *result unchanged on error.
    *result = address;
    return 0;
}
