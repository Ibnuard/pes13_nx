// SPDX-License-Identifier: MIT
#pragma once
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>

// Decoder-private address worklists. Keep the common, small case inside the
// decoder: no per-address malloc/free or PE/native callback. Oversized sets
// spill to the original ordered tree, preserving its unbounded capacity.
// No iterator escapes this class. A decoder belongs to a single FEX thread.
template<class Tree, size_t Capacity = 64>
class PES13FexDecodeSet {
    static_assert(Capacity > 0);
    std::array<uint64_t, Capacity> Values;
    size_t Count{};
    Tree Overflow;
    bool Spilled{};

public:
    bool Empty() const { return Spilled ? Overflow.empty() : Count == 0; }
    bool Contains(uint64_t value) const {
        return Spilled ? Overflow.contains(value) :
            std::binary_search(Values.begin(), Values.begin() + Count, value);
    }
    bool Insert(uint64_t value) {
        if (Spilled) return Overflow.insert(value).second;
        const auto end = Values.begin() + Count;
        const auto at = std::lower_bound(Values.begin(), end, value);
        if (at != end && *at == value) return false;
        if (Count == Capacity) {
            // Commit only after all allocations succeed. Partial spill failure
            // must leave the previous inline contents and ordering intact.
            Tree next;
            next.insert(Values.begin(), end);
            next.insert(value);
            Overflow.swap(next);
            Spilled = true;
            Count = 0;
            return true;
        }
        std::move_backward(at, end, end + 1);
        *at = value;
        ++Count;
        return true;
    }
    // Preconditions: nonempty. The decoder tests Empty before consuming work.
    uint64_t First() const { return Spilled ? *Overflow.begin() : Values[0]; }
    uint64_t PopFirst() {
        if (Spilled) {
            auto it = Overflow.begin();
            const auto value = *it;
            Overflow.erase(it);
            return value;
        }
        const auto value = Values[0];
        std::move(Values.begin() + 1, Values.begin() + Count, Values.begin());
        --Count;
        return value;
    }
    void Clear() {
        Overflow.clear();
        Spilled = false;
        Count = 0;
    }
    // Exactly the decoder's previous `destination.merge(source); source.clear()`
    // result: sorted union, duplicate targets discarded, source emptied. This
    // is deliberately not a replacement for general std::set::merge semantics.
    void MergeAndClear(PES13FexDecodeSet &source) {
        if (&source == this) return;
        if (Spilled && source.Spilled) {
            Overflow.merge(source.Overflow); // preserve node transfer on large sets
        } else if (source.Spilled) {
            for (auto value : source.Overflow) Insert(value);
        } else {
            for (size_t i = 0; i < source.Count; ++i) Insert(source.Values[i]);
        }
        source.Clear();
    }
};
