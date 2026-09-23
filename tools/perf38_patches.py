"""PERF36 execution preset plus scoped, control-flow-aware guard fusion."""
import perf34_patches
from perf17_patches import once

adapt_profile=perf34_patches.adapt_profile

def base36(project):
    path=project/'tools/perf36_patches.py'
    text=path.read_text().replace('local/perf36','local/perf38')
    for a,b in [('runtime-perf36-scoped-fastnan','runtime-perf38-region-fusion'),
                ('pes13-nx-0.2.0-perf36-scoped-fastnan','pes13-nx-0.2.0-perf38-region-fusion'),
                ('PES13-NX PERF36 FASTNAN','PES13-NX PERF38 FUSION')]:text=text.replace(a,b)
    ns={'__file__':str(path),'__name__':'perf38_base36'}
    exec(compile(text,str(path),'exec'),ns)
    return ns

def adapt(cmake,dynarec,runtime,project):
    cmake,dynarec,runtime=base36(project)['adapt'](cmake,dynarec,runtime,project)
    generated=project/'local/perf38/pes13_perf20_capture.h'
    text=generated.read_text()
    text=once(text,'#include "'+str(project/'src/runtime/pes13_perf20_fuse.h')+'"',
        '#include "'+str(project/'src/runtime/pes13_perf38.h')+'"')
    text=once(text,'r = pes20_fuse(db->block, db->native_size);','r = pes38_select_fusion(db);')
    text=once(text,'0x93e4e0, 0x923080, 0x1131240, 0x1120400,',
        '0x93e4e0, 0x923080, 0x113027b, 0x112f8f0,')
    text=once(text,'        struct pes17_snapshot *s = &pes17_snapshots[i];',
        '        struct pes17_snapshot *s = &pes17_snapshots[i];\n'
        '        if (i >= 6 && guest != pes20_targets[i]) continue;')
    generated.write_text(text)
    # Diagnostic-only captures need the complete 12 KiB hot block. The
    # quiet package leaves capture and sampling disabled.
    old=project/'src/runtime/pes13_perf17.h';new=project/'local/perf38/pes13_perf17_capture.h'
    text=once(old.read_text(),'#define PES17_ARM_BYTES 8192','#define PES17_ARM_BYTES 16384')
    new.write_text(text)
    dynarec=once(dynarec,'#include "'+str(old)+'"','#include "'+str(new)+'"')
    dynarec=once(dynarec,'    apply_box64_options();',
        '    apply_box64_options();\n    pes38_mode=wine_nx_config_file_bool(\n'
        '        "sdmc:/switch/pes13-nx/perf38-region-fusion.txt",0);')
    runtime=once(runtime,'    wine_nx_thread_report();',
        '    { extern void wine_nx_perf38_report(void); wine_nx_perf38_report(); }\n'
        '    wine_nx_thread_report();')
    return cmake,dynarec,runtime

def adapt_recipe(text):
    from pathlib import Path
    return base36(Path(__file__).resolve().parents[1])['adapt_recipe'](text)
