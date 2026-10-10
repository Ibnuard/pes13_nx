/* SPDX-License-Identifier: MIT
 * Exercise the real descriptor reader with injected filesystem failures.
 */
#include <array>
#include <cassert>
#include <cstring>
#include <iostream>
#include <memory>
#include <utility>
#include "../src/experimental/low_window/fextendo_memory_abi.hpp"

using Result = int;
using s64 = std::int64_t;
constexpr int Missing = 1, IoError = 2, Invalid = 3;
struct ScopeExitTag {};
template<class F> struct Guard { F f; ~Guard() { f(); } };
template<class F> Guard<F> operator+(ScopeExitTag, F f) { return {f}; }
#define ON_SCOPE_EXIT auto close_file = ScopeExitTag{} + [&]()
#define R_SUCCEED() return 0
#define R_TRY(x) do { const Result r = (x); if (r) return r; } while (0)
#define R_UNLESS(x, e) do { if (!(x)) return (e); } while (0)
#define ENCODE_ATMOSPHERE_CODE_PATH(x) "@Code:" x
namespace ams::svc {
    struct CreateProcessParameter { std::uint32_t flags; };
    constexpr auto CreateProcessFlag_FextendoLowWindow = fextendo::RequestFlag;
}
namespace ams::ldr { int ResultInvalidMeta() { return Invalid; } }
namespace ams::fs {
    struct FileHandle { int value; };
    constexpr int OpenMode_Read = 1;
    struct ResultPathNotFound { static bool Includes(Result r) { return r == Missing; } };
    struct State {
        int open = 0, stat = 0, read = 0, closed = 0, stats = 0, reads = 0;
        s64 size = 32;
        size_t read_size = 32;
        std::array<unsigned char, 32> bytes{};
    } state;
    Result OpenFile(FileHandle *file, const char *path, int mode) {
        assert(std::strcmp(path, "@Code:/fxtmem") == 0 && mode == OpenMode_Read);
        file->value = 77;
        return state.open;
    }
    void CloseFile(FileHandle file) { assert(file.value == 77); ++state.closed; }
    Result GetFileSize(s64 *out, FileHandle) { ++state.stats; *out = state.size; return state.stat; }
    Result ReadFile(size_t *out, FileHandle, int offset, void *dst, size_t size) {
        assert(offset == 0 && size == 32);
        ++state.reads;
        *out = state.read_size;
        std::memcpy(dst, state.bytes.data(), std::min(state.read_size, size));
        return state.read;
    }
}
namespace ams::ldr {
    #include "../src/experimental/low_window/ldr_fextendo_memory.inc"
}
static unsigned cases;
static void reset() {
    ams::fs::state = {};
    ams::fs::state.bytes = {'F','X','T','M','E','M',0,0, 1,0,0,0, 32,0,0,0, 1,0,0,0};
}
static void check(std::uint32_t flags, int expected) {
    ams::svc::CreateProcessParameter param{flags};
    const int status = ams::ldr::ApplyFextendoMemoryDescriptor(&param);
    assert(status == expected);
    const bool applied = status == 0 && ams::fs::state.open != Missing;
    assert(param.flags == (applied ? flags | ams::svc::fextendo::RequestFlag : flags));
    assert(ams::fs::state.closed == (ams::fs::state.open ? 0 : 1));
    ++cases;
}
int main() {
    constexpr std::uint32_t app39 = 0x67;
    reset(); check(app39, 0);
    reset(); ams::fs::state.open = Missing; check(app39, 0);
    assert(!ams::fs::state.stats && !ams::fs::state.reads);
    reset(); ams::fs::state.open = IoError; check(app39, IoError);
    reset(); ams::fs::state.stat = IoError; check(app39, IoError);
    reset(); ams::fs::state.read = IoError; check(app39, IoError);
    for (s64 size : {-1LL, 0LL, 1LL, 31LL, 33LL, 4096LL, 0x7fffffffffffffffLL}) {
        reset(); ams::fs::state.size = size; check(app39, Invalid);
        assert(ams::fs::state.reads == 0);
    }
    for (size_t n = 0; n < 32; ++n) {
        reset(); ams::fs::state.read_size = n; check(app39, Invalid);
    }
    for (size_t i = 0; i < 32; ++i) for (unsigned bit = 0; bit < 8; ++bit) {
        reset(); ams::fs::state.bytes[i] ^= 1u << bit; check(app39, Invalid);
    }
    // Exhaust every currently defined process flag combination, with and
    // without the private request bit. There is intentionally no program ID.
    for (std::uint32_t flags = 0; flags < 0x4000; ++flags) {
        const bool ok = (flags & 1) && ((flags >> 1) & 7) == 3 &&
            (flags & (1 << 6)) && ((flags >> 7) & 15) == 0 && !(flags & (1 << 13));
        for (auto extra : {0u, ams::svc::fextendo::RequestFlag}) {
            reset(); check(flags | extra, ok ? 0 : Invalid);
            reset(); ams::fs::state.open = Missing; check(flags | extra, 0);
        }
    }
    assert(!ams::svc::fextendo::ValidDescriptor(nullptr, 32));
    std::cout << "PASS " << cases << " descriptor, I/O, flag, and unchanged-default cases\n";
}
