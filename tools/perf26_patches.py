"""Compose PERF25 with one immutable game-environment option, CALLRET=2."""
from pathlib import Path
from perf17_patches import once
import perf25_patches

adapt_recipe=perf25_patches.adapt_recipe
adapt_profile=perf25_patches.adapt_profile

def policy_text(project):
    return once((project/'src/runtime/pes13_perf21.h').read_text(),
        '        pes21_env.is_any_overridden = 1;',
        '        pes21_env.is_any_overridden = 1;\n        pes26_configure(&pes21_env);')

def adapt(cmake,dynarec,runtime,project):
    # Generate the existing capture header in this experiment's own directory.
    path=project/'tools/perf25_patches.py'
    ns={'__file__':str(path),'__name__':'perf26_base'}
    exec(compile(path.read_text().replace('local/perf25','local/perf26'),str(path),'exec'),ns)
    cmake,dynarec,runtime=ns['adapt'](cmake,dynarec,runtime,project)
    header=project/'local/perf26/pes13_perf21_callret.h'
    header.write_text(policy_text(project))
    dynarec=once(dynarec,'#include "'+str(project/'src/runtime/pes13_perf21.h')+'"',
        '#include "'+str(project/'src/runtime/pes13_perf26.h')+'"\n#include "'+str(header)+'"')
    dynarec=once(dynarec,'    apply_box64_options();','''    apply_box64_options();
    {
        FILE *f = fopen("sdmc:/switch/pes13-nx/perf26-callret.txt", "r");
        if (f) { __atomic_store_n(&pes26_mode, fgetc(f) == '1', __ATOMIC_RELEASE); fclose(f); }
    }''')
    runtime=once(runtime,'    wine_nx_thread_report();',
        '    { extern void wine_nx_perf26_report(void); wine_nx_perf26_report(); }\n    wine_nx_thread_report();')
    return cmake,dynarec,runtime
