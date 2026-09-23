/* Grow ordinary PES text after first present. DLLs, the pinned matrix page,
 * startup lookup region and packed entry/other sections remain baseline. */
#ifndef PES13_PERF33_POLICY_H
#define PES13_PERF33_POLICY_H
#include <stdint.h>
static uintptr_t pes33_limit(uintptr_t address)
{
    static const uintptr_t ranges[][2] = {
        {0x401000,0x112f000},
        {0x1130000,0x1150000},
        {0x1170000,0x13d1000},
    };
    for (unsigned i=0; i<sizeof(ranges)/sizeof(*ranges); ++i)
        if (address>=ranges[i][0] && address<ranges[i][1]) return ranges[i][1];
    return 0;
}
#endif
