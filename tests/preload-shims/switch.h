#pragma once
#include <stddef.h>
#include <stdint.h>
typedef uint32_t Result;
typedef uint32_t u32;
typedef struct { uint64_t addr, size; uint32_t type, attr, perm; } MemoryInfo;
typedef struct VirtmemReservation VirtmemReservation;
#define MemType_Unmapped 0
#define R_FAILED(rc) ((rc) != 0)
void virtmemLock(void);
void virtmemUnlock(void);
Result svcQueryMemory(MemoryInfo *, u32 *, uint64_t);
VirtmemReservation *virtmemAddReservation(void *, size_t);
