/* One measured matrix sibling may use the existing per-block FASTROUND
 * environment. Keep the adjacent PERF19 native-patched block on box64env. */
#ifndef PES13_PERF41_H
#define PES13_PERF41_H

#define PES41_MATRIX_ADDR ((uintptr_t)0x112f8f0u)
#define PES41_MATRIX_BYTES 232u
#define PES41_MATRIX_END (PES41_MATRIX_ADDR + PES41_MATRIX_BYTES)
#define PES41_MATRIX_FNV UINT64_C(0xb04e420af1f912d6)

static int pes41_match_matrix(uintptr_t address)
{
    return address == PES41_MATRIX_ADDR &&
           pes40_hash_bytes((const void *)address, PES41_MATRIX_BYTES) == PES41_MATRIX_FNV;
}
#endif
