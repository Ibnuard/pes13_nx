#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "fextendo_guest_va.h"

int main(void)
{
    const uint64_t limit=UINT64_C(0x100000000);
    assert(fx_guest_va_ceiling(0x200000,0x40000000,limit,0)==0x20100000);
    assert(fx_guest_va_ceiling(0x200000,0x40000000,limit,1)==0x30000000);
    assert(!fx_guest_va_ceiling(0x200000,0x40000000,UINT64_C(1)<<39,1));
    assert(!fx_guest_va_ceiling(0x40000000,0x200000,limit,1));
    assert(!fx_guest_va_ceiling(0,0,limit,1));
    assert(!fx_guest_va_ceiling(0,0x40000000,0x20000000,1));
    for(uintptr_t start=0;start<0x40000000;start+=0x1740000)
        for(uintptr_t span=0x10000;span<0x60000000;span+=0x1920000)
            for(int enabled=0;enabled<2;enabled++){
                uintptr_t end=start+span,c=fx_guest_va_ceiling(start,end,limit,enabled);
                if(!c)continue;
                assert(c>start&&c<end&&c<=0x40000000&&!(c&0xffff));
                assert(end-c>=(enabled&&span>=0x20000000?0x10000000:span-span/2));
                if(span<0x20000000)assert(c==fx_guest_va_ceiling(start,end,limit,0));
            }
    puts("PASS: 32-bit VA partition; minimum native window; legacy control; small/invalid/large AS bounds");
}
