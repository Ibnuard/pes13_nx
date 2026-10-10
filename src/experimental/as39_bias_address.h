/* SPDX-License-Identifier: MIT
 * Experimental boundary conversion only. No page-table lookup in hot kernels.
 * These helpers validate the address domain, NOT page commitment/permissions.
 * A real Wine port must additionally validate the complete buffer lifetime.
 */
#ifndef PES13_AS39_BIAS_ADDRESS_H
#define PES13_AS39_BIAS_ADDRESS_H
#include <stddef.h>
#include <stdint.h>

static inline int as39_guest_span(uintptr_t bias, uint32_t guest, uint64_t length,
                                 uintptr_t *host) {
    if (!host || bias > UINTPTR_MAX - (UINT64_C(1) << 32)) return 0;
    if (!guest) {
        if (length) return 0;
        *host = 0;
        return 1;
    }
    if (length > (UINT64_C(1) << 32) - guest) return 0;
    *host = bias + guest;
    return 1;
}

static inline int as39_host_pointer(uintptr_t bias, uintptr_t host, uint32_t *guest) {
    if (!guest || bias > UINTPTR_MAX - (UINT64_C(1) << 32)) return 0;
    if (!host) { *guest = 0; return 1; }
    if (host <= bias || host - bias > UINT32_MAX) return 0;
    *guest = (uint32_t)(host - bias);
    return 1;
}
#endif
