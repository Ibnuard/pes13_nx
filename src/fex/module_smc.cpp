// SPDX-License-Identifier: MIT
#include <atomic>
#include <cstring>
#include "horizon_host.h"

namespace {
template<class T> T Read(uint64_t address) {
    T value;
    std::memcpy(&value, reinterpret_cast<const void *>(address), sizeof(value));
    return value;
}
bool IsImage(const char *path, const char *expected) {
    if (!path) return false;
    const char *base = path;
    for (const char *p = path; *p; ++p) if (*p == '/' || *p == '\\') base = p + 1;
    while (*base && *expected) {
        const unsigned char ch = *base++;
        if ((ch >= 'A' && ch <= 'Z' ? ch + 'a' - 'A' : ch) != *expected++) return false;
    }
    return !*base && !*expected;
}
}

extern "C" int PES13FexCanBatchSMC(uint64_t image, uint64_t image_size, const char *name,
                                   uint64_t address, uint64_t size) {
    // Box64 validates translated blocks at entry. Limit that experiment to
    // static .text in the game and renderer; unpackers/JITs/unknown DLLs keep
    // instruction-level checks. Bytes are STILL checked on every block entry.
    if (!image || image_size < 0x100 || image_size > UINT64_MAX - image ||
        !size || size > 65536 || address < image || address - image >= image_size ||
        size > image_size - (address - image) ||
        (!IsImage(name, "pes2013.exe") && !IsImage(name, "d3d9.dll"))) return 0;
    if (Read<uint16_t>(image) != 0x5a4d) return 0;
    const uint32_t pe = Read<uint32_t>(image + 0x3c);
    if (pe > image_size - 24 || Read<uint32_t>(image + pe) != 0x4550 ||
        Read<uint16_t>(image + pe + 4) != 0x14c) return 0;
    const uint16_t count = Read<uint16_t>(image + pe + 6);
    const uint16_t optional = Read<uint16_t>(image + pe + 20);
    const uint64_t table = uint64_t(pe) + 24 + optional;
    if (!count || count > 96 || table > image_size || uint64_t(count) * 40 > image_size - table) return 0;
    for (unsigned i = 0; i < count; ++i) {
        const uint64_t section = image + table + i * 40;
        const uint32_t length = Read<uint32_t>(section + 8);
        const uint32_t rva = Read<uint32_t>(section + 12);
        const uint32_t flags = Read<uint32_t>(section + 36);
        if (rva >= image_size || length > image_size - rva) continue;
        if (address - image < rva || size > length || address - image - rva > length - size) continue;
        return Read<uint64_t>(section) == 0x000000747865742eULL &&
               (flags & 0xe0000000u) == 0x60000000u;
    }
    return 0;
}

extern "C" void PES13FexRecordSMC(uint64_t instructions, unsigned mode) {
    // Compile counts, NOT execution samples or an FPS measurement. Bounded
    // reports allow the next device log to establish real policy coverage.
    static std::atomic<uint64_t> blocks{0}, full{0}, entry{0}, avoided{0};
    if (mode == 1) full.fetch_add(1, std::memory_order_relaxed);
    if (mode == 2) {
        entry.fetch_add(1, std::memory_order_relaxed);
        if (instructions) avoided.fetch_add(instructions - 1, std::memory_order_relaxed);
    }
    const auto count = blocks.fetch_add(1, std::memory_order_relaxed) + 1;
    if (count != 1 && (count % 4096 || count > 262144)) return;
    char message[180], *out = message;
    auto text = [&](const char *s) { while (*s) *out++ = *s++; };
    auto number = [&](uint64_t v) {
        char tmp[24]; unsigned n = 0;
        do { tmp[n++] = '0' + v % 10; v /= 10; } while (v);
        while (n) *out++ = tmp[--n];
    };
    text("[FEX3-SMC2] blocks="); number(count);
    text(" full="); number(full.load(std::memory_order_relaxed));
    text(" entry="); number(entry.load(std::memory_order_relaxed));
    text(" guard_branches_avoided="); number(avoided.load(std::memory_order_relaxed));
    *out = 0;
    PES13FexLog(message);
}

extern "C" void PES13FexLogSMCProtectFailure(uint64_t address, uint64_t size,
                                            uint32_t protect, uint32_t status) {
    // Error-only, bounded diagnostics. No allocation, printf or per-frame I/O.
    static std::atomic<unsigned> reports {0};
    if (reports.fetch_add(1, std::memory_order_relaxed) >= 8) return;
    char message[200];
    char *out = message;
    auto text = [&](const char *value) { while (*value) *out++ = *value++; };
    auto hex = [&](uint64_t value) {
        text("0x");
        for (int shift = 60; shift >= 0; shift -= 4)
            *out++ = "0123456789abcdef"[(value >> shift) & 15];
    };
    text("[FEX3-SMC] protection failed base="); hex(address);
    text(" size="); hex(size);
    text(" protect="); hex(protect);
    text(" status="); hex(status);
    *out = 0;
    PES13FexLog(message);
}
