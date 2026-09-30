// Differential semantics and allocation counts; host timing is not Switch FPS.
#include "horizon_decode_set.h"
#include <cassert>
#include <chrono>
#include <cstdio>
#include <limits>
#include <random>
#include <set>
#include <vector>

static size_t allocations, frees;
static int fail_after = -1;
template<class T> struct Allocator {
    using value_type = T;
    Allocator() = default;
    template<class U> Allocator(const Allocator<U>&) {}
    T* allocate(size_t n) {
        if (fail_after == 0) throw std::bad_alloc();
        if (fail_after > 0) --fail_after;
        ++allocations;
        return std::allocator<T>{}.allocate(n);
    }
    void deallocate(T* p, size_t n) { ++frees; std::allocator<T>{}.deallocate(p, n); }
    template<class U> bool operator==(const Allocator<U>&) const { return true; }
};
using Tree = std::set<uint64_t, std::less<uint64_t>, Allocator<uint64_t>>;
using Small = PES13FexDecodeSet<Tree>;

static void check_contents(Small& small, const Tree& reference) {
    for (auto value : reference) {
        assert(!small.Empty() && small.First() == value && small.Contains(value));
        assert(small.PopFirst() == value);
    }
    assert(small.Empty());
    small.Clear();
    for (auto value : reference) small.Insert(value);
}

static void differential() {
    std::mt19937_64 random(0x13fe);
    Small small[3]; Tree tree[3];
    for (size_t step = 0; step < 200000; ++step) {
        const auto which = random() % 3, other = (which + 1) % 3;
        const uint64_t value = step % 7 == 0 ? random() : random() % 256;
        auto& s = small[which]; auto& t = tree[which];
        switch (random() % 8) {
        case 0: s.Clear(); t.clear(); break;
        case 1:
            if (!t.empty()) { assert(s.PopFirst() == *t.begin()); t.erase(t.begin()); }
            break;
        case 2:
            s.MergeAndClear(small[other]);
            t.merge(tree[other]); tree[other].clear();
            assert(small[other].Empty());
            break;
        default: assert(s.Insert(value) == t.insert(value).second); break;
        }
        assert(s.Contains(value) == t.contains(value));
        assert(s.Empty() == t.empty());
        if (!t.empty()) assert(s.First() == *t.begin());
        if (step % 127 == 0) for (unsigned i = 0; i < 3; ++i) check_contents(small[i], tree[i]);
    }
    for (unsigned i = 0; i < 3; ++i) check_contents(small[i], tree[i]);
    // All inline/tree merge combinations, capacity boundaries, duplicate targets,
    // large JIT limits, unsigned extrema and return to inline storage after Clear.
    for (unsigned n : {0, 1, 63, 64, 65, 128, 5000}) {
        Small s, from; Tree t, tf;
        for (unsigned i = 0; i < n; ++i) { s.Insert(i * 2); t.insert(i * 2); }
        for (unsigned j : {1, 64, 65, 5000}) {
            for (unsigned i = 0; i < j; ++i) { from.Insert(i); tf.insert(i); }
            s.MergeAndClear(from); t.merge(tf); tf.clear();
            assert(from.Empty()); check_contents(s, t);
        }
        s.Insert(UINT64_MAX); t.insert(UINT64_MAX);
        s.Insert(0); t.insert(0); check_contents(s, t);
        s.Clear(); const auto before = allocations;
        for (unsigned i = 0; i < 64; ++i) assert(s.Insert(64 - i));
        assert(allocations == before);
        s.MergeAndClear(s); assert(!s.Empty());
    }
    // Failed overflow migration must not lose any of the original addresses.
    for (int failure : {0, 1, 32, 64}) {
        Small s;
        for (unsigned i = 0; i < 64; ++i) s.Insert(i);
        fail_after = failure;
        try { s.Insert(UINT64_MAX); assert(false); } catch (const std::bad_alloc&) {}
        fail_after = -1;
        for (unsigned i = 0; i < 64; ++i) assert(s.PopFirst() == i);
        assert(s.Empty());
    }
}

struct Baseline {
    Tree tree;
    bool Empty() const { return tree.empty(); }
    bool Contains(uint64_t v) const { return tree.contains(v); }
    bool Insert(uint64_t v) { return tree.insert(v).second; }
    uint64_t PopFirst() { auto it = tree.begin(); auto v = *it; tree.erase(it); return v; }
    void Clear() { tree.clear(); }
    void MergeAndClear(Baseline& other) { tree.merge(other.tree); other.tree.clear(); }
};
struct Result { size_t alloc, free; uint64_t checksum, ns; };
template<class Set> Result workload(unsigned blocks, unsigned repeats) {
    const auto before_alloc = allocations, before_free = frees;
    const auto begin = std::chrono::steady_clock::now();
    uint64_t checksum = 0;
    {
        Set visited, pending, targets;
        for (unsigned run = 0; run < repeats; ++run) {
            visited.Clear(); pending.Clear(); targets.Clear(); pending.Insert(0);
            while (!pending.Empty()) {
                auto pc = pending.PopFirst(); visited.Insert(pc);
                checksum += pc;
                for (auto target : {pc / 2, pc + 1, pc + 2})
                    if (target < blocks && !visited.Contains(target)) targets.Insert(target);
                pending.MergeAndClear(targets);
                targets.Clear();
            }
        }
    }
    return {allocations - before_alloc, frees - before_free, checksum,
        static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now() - begin).count())};
}

int main() {
    differential();
    assert(allocations == frees);
    std::puts("PASS 200000 randomized operations, all spill/merge boundaries, 5000 entries, failure preservation");
    for (unsigned blocks : {8, 32, 64, 128, 512}) {
        const unsigned repeats = blocks <= 64 ? 10000 : 1000;
        const auto old = workload<Baseline>(blocks, repeats), next = workload<Small>(blocks, repeats);
        assert(old.checksum == next.checksum && old.alloc == old.free && next.alloc == next.free);
        if (blocks <= 64) assert(next.alloc == 0);
        assert(next.alloc < old.alloc);
        std::printf("{\"blocks\":%u,\"runs\":%u,\"old_allocations\":%zu,\"new_allocations\":%zu,"
                    "\"old_host_ns\":%llu,\"new_host_ns\":%llu}\n", blocks, repeats,
                    old.alloc, next.alloc, (unsigned long long)old.ns, (unsigned long long)next.ns);
    }
    assert(allocations == frees);
}
