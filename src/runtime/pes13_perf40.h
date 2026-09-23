/* PES13-NX: one fingerprinted pre-present FASTROUND candidate. This is used
 * only while Box64 selects an environment for a new game block; no work is
 * added to the translated block or frame path. */
#ifndef PES13_PERF40_H
#define PES13_PERF40_H
#include <stddef.h>
#include <stdint.h>

#define PES40_EARLY_ADDR ((uintptr_t)0x113027bu)
#define PES40_EARLY_BYTES 1113u
#define PES40_EARLY_FNV UINT64_C(0x9bc4c221c199e08a)

static uint64_t pes40_hash_bytes(const void *data, size_t size)
{
    const unsigned char *bytes = data;
    uint64_t hash = UINT64_C(14695981039346656037);
    for (size_t i = 0; i < size; ++i)
        hash = (hash ^ bytes[i]) * UINT64_C(1099511628211);
    return hash;
}

static int pes40_match_early(uintptr_t address)
{
    return address == PES40_EARLY_ADDR &&
           pes40_hash_bytes((const void *)address, PES40_EARLY_BYTES) == PES40_EARLY_FNV;
}
#endif
