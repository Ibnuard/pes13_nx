// SPDX-License-Identifier: MIT
// Standalone native test of the permission-range policy used by FEX Core.cpp.
#include "../src/fex/horizon_smc.h"
#include <cassert>
#include <cstdio>
#include <vector>

struct Range { uint64_t Base, Size; bool Writable; };
static unsigned checks;
static void check(bool expected, uint64_t start, uint64_t size,
                  const std::vector<Range>& ranges) {
    unsigned queries = 0;
    const bool result = PES13FexNeedsCodeValidation(start, size, [&](uint64_t address) {
        assert(++queries <= ranges.size() + 1);
        for (const auto& range : ranges)
            if (address >= range.Base && address - range.Base < range.Size) return range;
        return Range {};
    });
    assert(result == expected);
    ++checks;
}
int main() {
    // RX code stays unchecked; RWX, boundary crossings and holes need guards.
    check(false, 0x1000, 0, {});
    check(false, 0x1000, 4096, {{0x1000, 4096, false}, {0x2000, 4096, true}});
    check(true, 0x1fff, 2, {{0x1000, 4096, false}, {0x2000, 4096, true}});
    check(true, 0x1fff, 2, {{0x1000, 4096, true}, {0x2000, 4096, false}});
    check(false, 0x1fff, 2, {{0x1000, 4096, false}, {0x2000, 4096, false}});
    check(true, 0x1000, 4096, {{0x1000, 2048, false}, {0x1801, 2047, false}});
    check(true, UINT64_MAX - 1, 2, {});
    check(true, UINT64_MAX - 7, 3, {{UINT64_MAX - 16, 32, false}});
    for (const auto malformed : {Range {0x1001, 1, false}, Range {0xffe, 2, false}, Range {0, 0, false}}) {
        assert(PES13FexNeedsCodeValidation(0x1000, 1, [&](uint64_t) { return malformed; }));
        ++checks;
    }
    // Exhaustive small-region oracle, independently evaluated byte-by-byte.
    for (unsigned layout = 0; layout != 16; ++layout) {
        std::vector<Range> ranges;
        for (unsigned i = 0; i != 4; ++i) ranges.push_back({0x1000+i*5, 5, bool(layout & (1 << i))});
        for (unsigned offset = 0; offset != 20; ++offset) {
            for (unsigned length = 0; length <= 20-offset; ++length) {
                bool expected = false;
                for (unsigned b = offset; b != offset+length; ++b) expected |= bool(layout & (1 << (b/5)));
                check(expected, 0x1000+offset, length, ranges);
            }
        }
    }
    std::printf("{\"passed\":true,\"checks\":%u,\"scope\":\"permission interval selection, not device execution\"}\n", checks);
}
