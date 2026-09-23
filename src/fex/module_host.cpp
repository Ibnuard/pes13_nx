// SPDX-License-Identifier: MIT
#include "horizon_host.h"

static_assert(sizeof(pes13_fex_host) == 56);
static_assert(offsetof(pes13_fex_host, allocate_code) == 16);

extern "C" uint64_t PES13FexCallHost(uintptr_t callback, uint64_t arg0, uint64_t arg1);

namespace {
pes13_fex_host Host {};
bool Ready {};

template<typename Callback>
uint64_t CallHost(Callback callback, uint64_t arg0, uint64_t arg1 = 0) {
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
}

extern "C" int PES13FexSetHost(const pes13_fex_host *host) {
    if (Ready || !host || host->magic != PES13_FEX_HOST_MAGIC ||
        host->version != PES13_FEX_HOST_ABI || host->size != sizeof(Host) ||
        host->reserved || !host->allocate_code || !host->release_code ||
        !host->write_alias || !host->flush_code || !host->log) return 0;
    Host = *host;
    Ready = true;
    PES13FexLog("[FEX-HOST] ABI 1 installed; dual mapping enabled; x18 guarded");
    return 1;
}

extern "C" int PES13FexHostReady(void) { return Ready; }
extern "C" void PES13FexLog(const char *message) {
    if (Ready && message) CallHost(Host.log, reinterpret_cast<uintptr_t>(message));
}

extern "C" void PES13FexHostPreflight(void) {
    const uintptr_t teb = CurrentTeb();
    if (!Ready || !teb) Fail("[FEX2-ABI] STOP missing host or Wine TEB");
    PES13FexLog("[FEX2-ABI] v4 checking PE/native callback preserves x18");
    if (CurrentTeb() != teb) Fail("[FEX2-ABI] STOP Wine TEB changed after host callback");
    PES13FexLog("[FEX2-ABI] PASS callback preserves Wine TEB");
}

extern "C" void *PES13FexAllocateCode(uint64_t size) {
    if (!Ready) Fail("[FEX-HOST] missing host before JIT allocation");
    void *result = reinterpret_cast<void *>(CallHost(Host.allocate_code, size));
    if (!result) Fail("[FEX-HOST] executable allocation failed");
    return result;
}

extern "C" int PES13FexReleaseCode(void *rx) {
    if (!Ready) Fail("[FEX-HOST] missing host before JIT release");
    int result = static_cast<int>(CallHost(Host.release_code, reinterpret_cast<uintptr_t>(rx)));
    if (result < 0) Fail("[FEX-HOST] executable release failed");
    return result;
}

extern "C" void *PES13FexWriteAlias(const void *address, uint64_t size) {
    if (!Ready) Fail("[FEX-HOST] missing host before code write");
    void *result = reinterpret_cast<void *>(CallHost(Host.write_alias, reinterpret_cast<uintptr_t>(address), size));
    if (!result && size) Fail("[FEX-HOST] code write crossed allocation boundary");
    return result;
}

extern "C" void PES13FexFlushCode(const void *address, uint64_t size) {
    if (!Ready || !static_cast<int>(CallHost(Host.flush_code, reinterpret_cast<uintptr_t>(address), size)))
        Fail("[FEX-HOST] invalid instruction-cache flush");
}
