"""Narrow, fingerprinted REP MOVSD optimization on the PERF24 runtime."""
import perf24_patches
from perf17_patches import once

adapt_recipe=perf24_patches.adapt_recipe
adapt_profile=perf24_patches.adapt_profile

def adapt(cmake,dynarec,runtime,project):
    cmake,dynarec,runtime=perf24_patches.adapt(cmake,dynarec,runtime,project)
    # Reserve one snapshot without changing earlier experiments' headers.
    original=project/'src/runtime/pes13_perf20.h'
    capture=once(original.read_text(), '#include "pes13_perf20_fuse.h"',
        '#include "'+str(project/'src/runtime/pes13_perf20_fuse.h')+'"')
    capture=once(capture,'    for (i = 0; i < PES17_SLOTS; ++i) {',
        '    for (i = 0; i < PES17_SLOTS; ++i) {\n        if (i == 5) continue; /* PERF25 startup fault capture */')
    generated=project/'local/perf25/pes13_perf20_capture.h'
    generated.write_text(capture)
    dynarec=once(dynarec,'#include "'+str(original)+'"','#include "'+str(generated)+'"')
    anchor='#include "'+str(project/'src/runtime/pes13_perf22.h')+'"'
    dynarec=once(dynarec,anchor,anchor+'\n#include "'+str(project/'src/runtime/pes13_perf25.h')+'"')
    dynarec=once(dynarec,'    apply_box64_options();','''    apply_box64_options();
    {
        FILE *f = fopen("sdmc:/switch/pes13-nx/perf25-paircopy.txt", "r");
        if (f) { __atomic_store_n(&pes25_mode, fgetc(f) == '1', __ATOMIC_RELEASE); fclose(f); }
    }''')
    cmake=once(cmake,'extern void wine_nx_perf22_completed(void*, const void*); wine_nx_perf22_completed(block, helper.env);',
        'extern void wine_nx_perf25_completed(void*, const void*); wine_nx_perf25_completed(block, helper.env);')
    old='''                TBNZ_MARK2(xFlags, F_DF);
                MARK;   // Part with DF==0
                LDRxw_S9_postindex(x1, xRSI, rex.w?8:4);
                STRxw_S9_postindex(x1, xRDI, rex.w?8:4);'''
    new='''                TBNZ_MARK2(xFlags, F_DF);
                if (rex.is32bits && !rex.is67 && !rex.w &&
                    wine_nx_perf25_copy(dyn->insts[ninst].x64.addr, dyn->env)) {
                    PES25_COPY_FORWARD();
                }
                MARK;   // Part with DF==0
                LDRxw_S9_postindex(x1, xRSI, rex.w?8:4);
                STRxw_S9_postindex(x1, xRDI, rex.w?8:4);'''
    patch='''    wine_nx_box64_patch(opcodes_source [=[%s]=] [=[%s]=] "PERF25 fingerprinted REP MOVSD pair loop")
    string(PREPEND opcodes_source [=[#include <stdint.h>
#include "%s"
extern int wine_nx_perf25_copy(uintptr_t, const void*);
]=])
'''%(old,new,str(project/'src/runtime/pes13_perf25_copy_emit.h'))
    anchor='    set(opcodes_generated "${CMAKE_CURRENT_BINARY_DIR}/${target}-dynarec_arm64_00.c")'
    cmake=once(cmake,anchor,patch+anchor)
    runtime=once(runtime,'    wine_nx_thread_report();',
        '    { extern void wine_nx_perf25_report(void); wine_nx_perf25_report(); }\n    wine_nx_thread_report();')
    return cmake,dynarec,runtime
