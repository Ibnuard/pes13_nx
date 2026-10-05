#include <assert.h>
#include <stdio.h>
#include "../src/runtime/fextendo_launch_memory.h"
int main(void){
    struct fx_launch_memory m={.base=0x200000,.size=0xffe00000};
    assert(fx_memory_mode(&m)==FX_MEMORY_32_NO_ALIAS);
    m.alias=0x40000000;assert(fx_memory_mode(&m)==FX_MEMORY_32_ALIAS);
    m=(struct fx_launch_memory){.base=0x8000000,.size=0xff8000000,.alias=0x180000000};
    assert(fx_memory_mode(&m)==FX_MEMORY_36);
    m=(struct fx_launch_memory){.base=0x8000000,.size=(1ull<<39)-0x8000000,.alias=1ull<<36};
    assert(fx_memory_mode(&m)==FX_MEMORY_39);
    m.size=(1ull<<42)-m.base;assert(fx_memory_mode(&m)==FX_MEMORY_42);
    m=(struct fx_launch_memory){.base=0x200000,.size=0xffe00000};
    m.base_rc=1;assert(fx_memory_mode(&m)==FX_MEMORY_UNKNOWN);m.base_rc=0;
    m.size_rc=1;assert(fx_memory_mode(&m)==FX_MEMORY_UNKNOWN);m.size_rc=0;
    m.alias_rc=1;assert(fx_memory_mode(&m)==FX_MEMORY_UNKNOWN);m.alias_rc=0;
    m.total_rc=1;assert(fx_memory_mode(&m)==FX_MEMORY_32_NO_ALIAS); /* budget is informational */
    m.base=UINT64_MAX-16;m.size=64;assert(fx_memory_mode(&m)==FX_MEMORY_UNKNOWN);
    m.base=0;m.size=0;assert(fx_memory_mode(&m)==FX_MEMORY_UNKNOWN);
    m.size=0x1000;assert(fx_memory_mode(&m)==FX_MEMORY_UNKNOWN);
    puts("Address-space classification: no-alias vs alias, 36/39/42-bit, failed queries and invalid ranges passed.");
}
