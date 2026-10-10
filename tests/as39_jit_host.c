/* SPDX-License-Identifier: MIT
 * Host validation of the unchanged FEX native adapter, using actual shared
 * mappings above 4 GiB. This does not emulate x86 through FEXCore. */
#include "horizon_host.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    const struct pes13_fex_host *host = pes13_fex_native_host();
    for (int i = 0; i < 64; ++i) {
        void *rx = host->allocate_code(4096);
        assert(rx && (uintptr_t)rx > UINT32_MAX);
        uint8_t *rw = host->write_alias(rx, 4096);
        assert(rw && rw != rx && (uintptr_t)rw > UINT32_MAX);
        assert(!host->write_alias((char *)rx + 4095, 2));
        /* Native x86-64 host: mov eax,42; ret. */
        const uint8_t code[] = {0xb8, 42, 0, 0, 0, 0xc3};
        memcpy(rw, code, sizeof(code));
        assert(host->flush_code(rx, sizeof(code)));
        assert(((uint32_t (*)(void))rx)() == 42);
        rw[1] = 85;
        assert(host->flush_code(rx, sizeof(code)));
        assert(((uint32_t (*)(void))rx)() == 85);
        assert(host->release_code(rx) == 1);
    }
    void *slots[64];
    for (unsigned i = 0; i < 64; ++i) { slots[i] = host->allocate_code(4096); assert(slots[i]); }
    assert(!host->allocate_code(4096));
    for (unsigned i = 0; i < 64; ++i) assert(host->release_code(slots[i]) == 1);
    void *again = host->allocate_code(4096);
    assert(again && host->release_code(again) == 1);
    puts("PASS real host aliases above 4 GiB: execute/backpatch/reuse x64, 64-slot exhaustion and recovery");
    return 0;
}
