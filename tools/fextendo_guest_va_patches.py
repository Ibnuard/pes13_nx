"""Protect more contiguous guest VA before native aliases fragment it."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def apply(source,feature):
    name='dlls/ntdll/unix/virtual.c';p=source/name;data=p.read_text()
    def one(text,old,new):
        assert text.count(old)==1,(old[:100],text.count(old))
        return text.replace(old,new)
    header='dlls/ntdll/unix/fextendo_guest_va.h'
    (source/header).write_bytes((ROOT/'src/runtime/fextendo_guest_va.h').read_bytes())
    anchor='static void horizon_reserve_guest_address_space(void)\n'
    data=one(data,anchor,'''#include "fextendo_guest_va.h"
static int horizon_guest_va_headroom=1;
void horizon_guest_va_set_headroom(int enabled) { horizon_guest_va_headroom=!!enabled; }
static void __attribute__((noinline)) horizon_reserve_guest_address_space(void)
''')
    start=data.index('    /* virtmemFindStack cannot use arbitrary ASLR addresses.')
    end=data.index('    for (range = free_ranges;',start)
    data=data[:start]+'''    /* Reserve virtual addresses only; backing is still committed on demand.
     * A 32-bit 1022-MiB stack region leaves at least 256 MiB for libnx stacks.
     * reserve_area preserves kernel mappings, Wine views and native owners. */
    reserve_end=(char *)fx_guest_va_ceiling((ULONG_PTR)stack_start,(ULONG_PTR)stack_end,
                                          (ULONG_PTR)host_addr_space_limit,horizon_guest_va_headroom);
    if (!reserve_end) return;
    snprintf(msg,sizeof(msg),"[VA-PARTITION] v1 headroom=%d stack=%p-%p guest_end=%p native_window_mb=%lu",
             horizon_guest_va_headroom,stack_start,stack_end,reserve_end,
             (unsigned long)(((char *)stack_end-reserve_end)>>20));
    wine_nx_runtime_trace(msg);
'''+data[end:]
    p.write_text(data)
    name2='wine-nx-probe/source/runtime.c';p=source/name2;data=p.read_text()
    anchor='    pes13_fex_set_performance_profile(fex_profile);'
    data=one(data,anchor,anchor+'''
    {
        extern void horizon_guest_va_set_headroom(int enabled);
        horizon_guest_va_set_headroom(wine_nx_config_file_bool(RUNTIME_DIR "/guest_va_headroom",1));
    }''')
    p.write_text(data)
    return {name,name2,header}
