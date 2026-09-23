"""PERF28 plus measured-region block growth, preserving the existing math policy."""
import perf28_patches
from perf17_patches import once
adapt_profile=perf28_patches.adapt_profile

def adapt_recipe(text):
    return perf28_patches.adapt_recipe(text).replace('local/perf28','local/perf29')

def copy_header(project):
    old=project/'src/runtime/pes13_perf25.h'
    header=once(old.read_text(),'#include "pes13_perf25_policy.h"',
        '#include "'+str(project/'src/runtime/pes13_perf25_policy.h')+'"\n'
        'extern const void *wine_nx_perf29_base(const void *);')
    return once(header,'    if (ip!=0x93df43) return 0;',
        '    if (ip!=0x93df43) return 0;\n    env=wine_nx_perf29_base(env);')

def adapt(cmake,dynarec,runtime,project):
    path=project/'tools/perf28_patches.py';ns={'__file__':str(path),'__name__':'perf29_base'}
    exec(compile(path.read_text().replace("'local/perf28'","'local/perf29'"),str(path),'exec'),ns)
    cmake,dynarec,runtime=ns['adapt'](cmake,dynarec,runtime,project)
    old=project/'src/runtime/pes13_perf25.h'
    generated=project/'local/perf29/pes13_perf25_env.h'
    generated.write_text(copy_header(project))
    dynarec=once(dynarec,'#include "'+str(old)+'"',
        '#include "'+str(generated)+'"\n#include "'+str(project/'src/runtime/pes13_perf29.h')+'"')
    dynarec=once(dynarec,'return pes22_select(addr);','return pes29_select(addr,pes22_select(addr));')
    dynarec=once(dynarec,'    apply_box64_options();','''    apply_box64_options();
    {
        FILE *f=fopen("sdmc:/switch/pes13-nx/perf29-worker-blocks.txt","r");
        if (f) { pes29_mode=fgetc(f)=='1'; fclose(f); }
    }''')
    cmake=once(cmake,'extern uintptr_t wine_nx_perf22_block_end(uintptr_t, uintptr_t, const void*); helper.end = wine_nx_perf22_block_end(addr, helper.end, helper.env);',
        'extern uintptr_t wine_nx_perf29_block_end(uintptr_t, uintptr_t, const void*); helper.end = wine_nx_perf29_block_end(addr, helper.end, helper.env);')
    cmake=once(cmake,'extern void wine_nx_perf25_completed(void*, const void*); wine_nx_perf25_completed(block, helper.env);',
        'extern void wine_nx_perf29_completed(void*, const void*); wine_nx_perf29_completed(block, helper.env);')
    runtime=once(runtime,'    wine_nx_thread_report();',
        '    { extern void wine_nx_perf29_report(void); wine_nx_perf29_report(); }\n    wine_nx_thread_report();')
    return cmake,dynarec,runtime
