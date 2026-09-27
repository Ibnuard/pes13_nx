/* LGPL-2.1-or-later. Policy for automatic Wine worker placement only.
 * Guest-visible processor masks and explicit affinities stay unchanged.
 * Keep a valid fallback on hosts granting only core 3 or other cores. */
#ifndef PES13_FEX_WORKER_CORES_H
#define PES13_FEX_WORKER_CORES_H
#include <stdint.h>
extern int wine_nx_fex_auto_core3;
static inline uint64_t fex_auto_worker_mask(uint64_t available, int allow_core3)
{
    const uint64_t preferred = available & 7;
    return allow_core3 || !preferred ? available : preferred;
}
#endif
