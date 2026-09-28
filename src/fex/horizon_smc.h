// SPDX-License-Identifier: MIT
#pragma once
#include <cstdint>

// Called once per decoded block, while FEX holds its compilation/invalidation
// lock. Walk every permission interval: an instruction or block can straddle
// RX and RWX memory. Unknown or inconsistent ranges conservatively need a
// guard; they must never silently select the unchecked path.
template<typename Query>
bool PES13FexNeedsCodeValidation(uint64_t address, uint64_t size, Query query) {
    if (!size) return false;
    if (size > UINT64_MAX - address) return true;
    const uint64_t end = address + size;
    while (address < end) {
        const auto range = query(address);
        if (!range.Size || range.Base > address || range.Size > UINT64_MAX - range.Base)
            return true;
        const uint64_t range_end = range.Base + range.Size;
        if (range_end <= address || range.Writable) return true;
        address = range_end < end ? range_end : end;
    }
    return false;
}
