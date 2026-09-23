"""PERF25 runtime plus scoped block growth; retain its driver and synchronization."""
import perf25_patches
from perf17_patches import once
adapt_profile=perf25_patches.adapt_profile
adapt_recipe=perf25_patches.adapt_recipe

def copy_header(project):
    old=project/'src/runtime/pes13_perf25.h'
    header=once(old.read_text(),'#include "pes13_perf25_policy.h"',
        '#include "'+str(project/'src/runtime/pes13_perf25_policy.h')+'"\n'
        'extern const void *wine_nx_perf33_base(const void *);')
    return once(header,'    if (ip!=0x93df43) return 0;',
        '    if (ip!=0x93df43) return 0;\n    env=wine_nx_perf33_base(env);')

def adapt(cmake,dynarec,runtime,project):
    path=project/'tools/perf25_patches.py';ns={'__file__':str(path),'__name__':'perf33_base25'}
    exec(compile(path.read_text().replace('local/perf25','local/perf33'),str(path),'exec'),ns)
    cmake,dynarec,runtime=ns['adapt'](cmake,dynarec,runtime,project)
    old=project/'src/runtime/pes13_perf25.h'
    generated=project/'local/perf33/pes13_perf25_env.h'
    generated.write_text(copy_header(project))
    dynarec=once(dynarec,'#include "'+str(old)+'"',
        '#include "'+str(generated)+'"\n#include "'+str(project/'src/runtime/pes13_perf33.h')+'"')
    dynarec=once(dynarec,'return pes22_select(addr);','return pes33_select(addr,pes22_select(addr));')
    dynarec=once(dynarec,'    apply_box64_options();','''    apply_box64_options();
    {
        FILE *f=fopen("sdmc:/switch/pes13-nx/perf33-blocks.txt","r");
        if (f) { pes33_mode=fgetc(f)=='1'; fclose(f); }
    }''')
    cmake=once(cmake,'extern uintptr_t wine_nx_perf22_block_end(uintptr_t, uintptr_t, const void*); helper.end = wine_nx_perf22_block_end(addr, helper.end, helper.env);',
        'extern uintptr_t wine_nx_perf33_block_end(uintptr_t, uintptr_t, const void*); helper.end = wine_nx_perf33_block_end(addr, helper.end, helper.env);')
    cmake=once(cmake,'extern void wine_nx_perf25_completed(void*, const void*); wine_nx_perf25_completed(block, helper.env);',
        'extern void wine_nx_perf33_completed(void*, const void*); wine_nx_perf33_completed(block, helper.env);')
    runtime=once(runtime,'    wine_nx_thread_report();',
        '    { extern void wine_nx_perf33_report(void); wine_nx_perf33_report(); }\n    wine_nx_thread_report();')
    runtime=once(runtime,'wine-nx-runtime: generic Wine ntdll PE loader path',
        'PES13-NX: custom Horizon runtime (Wine / Box64 / DXVK / Mesa NVK)')
    return cmake,dynarec,runtime
