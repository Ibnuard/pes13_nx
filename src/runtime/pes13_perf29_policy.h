/* Compile-time selection for measured PES worker/CRT regions only. */
#ifndef PES13_PERF29_POLICY_H
#define PES13_PERF29_POLICY_H
#include <stdint.h>
static uintptr_t pes29_limit(uintptr_t address)
{
    static const uintptr_t ranges[][2] = {
        {0x920000,0x950000},
        {0x1100000,0x112f000}, /* exclude the fingerprinted PERF19 matrix page */
        {0x1130000,0x1150000}, /* exclude the recurring startup lookup at 115c36f */
        {0x1170000,0x11b0000},
    };
    for (unsigned i=0; i<sizeof(ranges)/sizeof(*ranges); ++i)
        if (address>=ranges[i][0] && address<ranges[i][1]) return ranges[i][1];
    return 0;
}
#endif
