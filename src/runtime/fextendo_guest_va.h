/* LGPL-2.1-or-later. Startup VA partition, not committed physical memory.
 * Leave native libnx stacks a real allowed interval. Never reserve the whole
 * stack region and never apply the 32-bit policy to a larger address space. */
#ifndef FEXTENDO_GUEST_VA_H
#define FEXTENDO_GUEST_VA_H
#include <stdint.h>

static uintptr_t fx_guest_va_ceiling(uintptr_t start,uintptr_t end,
                                     uint64_t host_limit,int headroom)
{
    const uintptr_t mib=1024u*1024u,mask=0xffff;
    uintptr_t span,keep,ceiling;
    if(host_limit>UINT64_C(0x100000000)||end<=start||end>host_limit)return 0;
    span=end-start;
    keep=span-span/2; /* Original half-region policy, also for small regions. */
    if(headroom&&span>=512u*mib){
        keep=span/4;
        if(keep<256u*mib)keep=256u*mib;
    }
    ceiling=end-keep;
    if(ceiling>0x40000000u)ceiling=0x40000000u;
    ceiling&=~mask;
    return ceiling>start?ceiling:0;
}
#endif
