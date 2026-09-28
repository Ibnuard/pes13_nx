// SPDX-License-Identifier: MIT
// Exercise the real host adapter with separate memory mappings and FEX's
// patched emitter. This does not execute an x86 guest through FEXCore.
#include "horizon_host.h"
#include <CodeEmitter/Buffer.h>
#include <cstdint>
#include <cstdio>
#include <cstring>
#ifdef PES13_FEX_FULL_EMITTER
#include <CodeEmitter/Emitter.h>
#include <cstdlib>
#include <atomic>
#include <thread>
namespace FEXCore::Allocator {
void *aligned_alloc(size_t alignment, size_t size) {
    void *result = nullptr;
    if (alignment < sizeof(void *)) alignment = sizeof(void *);
    return ::posix_memalign(&result, alignment, size) ? nullptr : result;
}
void aligned_free(void *ptr) { std::free(ptr); }
}
#endif

#define CHECK(expr) do { if (!(expr)) { std::printf("FAIL line %d: %s\n", __LINE__, #expr); return __LINE__; } } while (0)

extern "C" int pes13_fex_jit_test(void) {
    const auto *host = pes13_fex_native_host();
    pes13_fex_host bad = *host;
    CHECK(!PES13FexSetHost(nullptr));
    bad.version++;
    CHECK(!PES13FexSetHost(&bad));
    bad = *host;
    bad.flush_code = nullptr;
    CHECK(!PES13FexSetHost(&bad));
    CHECK(PES13FexSetHost(host));
    CHECK(!PES13FexSetHost(host));
    CHECK(PES13FexHostReady());
    CHECK(!host->allocate_scratch(0));
    auto *scratch = static_cast<uint8_t *>(host->allocate_scratch(16 * 1024 * 1024));
    CHECK(scratch && !(reinterpret_cast<uintptr_t>(scratch) & 4095));
    scratch[0] = 0x5a;
    scratch[16 * 1024 * 1024 - 1] = 0xa5;
    CHECK(scratch[0] == 0x5a && scratch[16 * 1024 * 1024 - 1] == 0xa5);
    host->release_scratch(scratch);
    CHECK(!host->allocate_code(0));
    CHECK(!host->allocate_code(UINT64_MAX));

    auto *rx = static_cast<uint8_t *>(host->allocate_code(4096));
    CHECK(rx);
    auto *rw = static_cast<uint8_t *>(host->write_alias(rx, 4096));
    CHECK(rw && rw != rx);
    CHECK(host->write_alias(rx + 8, 8) == rw + 8);
    CHECK(host->write_alias(rw + 8, 8) == rw + 8);
    CHECK(host->write_alias(rx + 4092, 8) == nullptr);
    CHECK(host->write_alias(reinterpret_cast<void *>(UINTPTR_MAX - 4), 8) == nullptr);
    CHECK(!host->flush_code(rx + 4092, 8));
    CHECK(host->release_code(rx + 8) == -1);
    CHECK(host->release_code(rw) == -1);
    uint8_t ordinary[32] {};
    CHECK(host->write_alias(ordinary, sizeof(ordinary)) == ordinary);
    CHECK(host->release_code(ordinary) == 0);

    ARMEmitter::Buffer code(rx, 4096);
    code.dc32(0x52800540); // mov w0, #42
    code.dc32(0xd65f03c0); // ret
    code.EmitString("alias");
    code.Align(16);
    CHECK(code.GetCursorOffset() == 16);
    CHECK(*reinterpret_cast<uint32_t *>(rx) == 0x52800540);
    CHECK(std::memcmp(rx + 8, "alias", 5) == 0);
    CHECK(rx[13] == 0 && rx[14] == 0 && rx[15] == 0);
    code.ClearICache(rx, 16);
#if defined(__aarch64__)
    using GeneratedFn = uint32_t (*)();
    auto call = reinterpret_cast<GeneratedFn>(rx);
    CHECK(call() == 42);
    code.SetCursorOffset(0);
    code.dc32(0x52800aa0); // mov w0, #85, same RX pointer after backpatch
    code.ClearICache(rx, 4);
    CHECK(call() == 85);
    std::puts("PASS ARM64 emitted code: 42 -> patch -> 85");
#else
    // Execute native host instructions to validate mapping permissions; the
    // ARM64 words above are checked as data on this host, not emulated.
    const uint8_t host_code[] = {0xb8, 42, 0, 0, 0, 0xc3};
    std::memcpy(rw, host_code, sizeof(host_code));
    CHECK(host->flush_code(rx, sizeof(host_code)));
    auto call = reinterpret_cast<uint32_t (*)()>(rx);
    CHECK(call() == 42);
    rw[1] = 85;
    CHECK(host->flush_code(rx, sizeof(host_code)));
    CHECK(call() == 85);
    std::puts("PASS native x86 host mapping execution (not FEX guest execution)");
#endif

#ifdef PES13_FEX_FULL_EMITTER
    // Real forward-label binding must use RX offsets and write through RW.
    ARMEmitter::Emitter emitter(rx, 4096);
    ARMEmitter::ForwardLabel label;
    (void)emitter.b(&label);
    emitter.nop();
    CHECK(emitter.Bind(&label));
    emitter.ret();
    CHECK(*reinterpret_cast<uint32_t *>(rx) == 0x14000002);
    emitter.ClearICache(rx, emitter.GetCursorOffset());
    std::puts("PASS FEX forward branch: canonical RX delta, RW backpatch");
#endif

    CHECK(host->release_code(rx) == 1);
    void *slots[8] {};
    for (auto &slot : slots) { slot = host->allocate_code(4096); CHECK(slot); }
    CHECK(!host->allocate_code(4096));
    for (auto slot : slots) CHECK(host->release_code(slot) == 1);
    rx = static_cast<uint8_t *>(host->allocate_code(4096));
    CHECK(rx);
    CHECK(host->release_code(rx) == 1);
    std::puts("PASS alias bounds, pool exhaustion, release and reuse");
#ifdef PES13_FEX_FULL_EMITTER
    // Scan/reuse other slots while each worker retains its own buffer.
    pes13_fex_set_logger(nullptr);
    std::atomic<bool> failed {false};
    std::thread workers[4];
    for (auto &worker : workers) worker = std::thread([&] {
        for (unsigned i = 0; i < 300; ++i) {
            auto *code = static_cast<uint8_t *>(host->allocate_code(4096));
            if (!code) { failed = true; return; }
            auto *write = static_cast<uint8_t *>(host->write_alias(code, 4096));
            if (!write || write == code) { failed = true; return; }
            std::memset(write, i & 255, 4096);
            if (code[27] != (i & 255) || !host->flush_code(code, 64)) failed = true;
            if (host->release_code(code) != 1) { failed = true; return; }
        }
    });
    for (auto &worker : workers) worker.join();
    CHECK(!failed);
    std::puts("PASS concurrent allocation/lookup/retirement: 4 threads x 300 mappings");
#endif
    return 0;
}

#ifndef __SWITCH__
int main() {
    pes13_fex_set_logger([](const char *message) { std::puts(message); });
    return pes13_fex_jit_test();
}
#endif
