"""PERF36 execution policy with bounded, sample-only JIT attribution."""
import perf34_patches
from perf17_patches import once

def base36(project):
    path=project/'tools/perf36_patches.py'
    text=path.read_text().replace('local/perf36','local/perf37')
    text=text.replace('runtime-perf36-scoped-fastnan','runtime-perf37-jit-probe')
    text=text.replace('pes13-nx-0.2.0-perf36-scoped-fastnan','pes13-nx-0.2.0-perf37-jit-probe')
    text=text.replace('PES13-NX PERF36 FASTNAN','PES13-NX PERF37 JIT PROBE')
    ns={'__file__':str(path),'__name__':'perf37_base36'}
    exec(compile(text,str(path),'exec'),ns)
    return ns

def adapt(cmake,dynarec,runtime,project):
    cmake,dynarec,runtime=base36(project)['adapt'](cmake,dynarec,runtime,project)
    anchor='int wine_nx_box64_pc_to_x86( uintptr_t pc, uintptr_t *x86 )'
    includes=''.join('#include "'+str(project/'src/runtime'/name)+'"\n' for name in
                     ('pes13_perf37_probe.h','pes13_perf37_sample.h'))
    dynarec=once(dynarec,anchor,includes+anchor)
    runtime=once(runtime,'    wine_nx_thread_report();',
        '    { static int reported; if (!reported) { reported=1;\n'
        '      log_line("[PERF37] sampled JIT opcode/block attribution; PERF36 execution policy unchanged"); } }\n'
        '    wine_nx_thread_report();')
    return cmake,dynarec,runtime

def adapt_recipe(text):
    from pathlib import Path
    return base36(Path(__file__).resolve().parents[1])['adapt_recipe'](text)

def adapt_profile(text,project):
    text=perf34_patches.adapt_profile(text,project)
    text=once(text,'struct nx_prof_target\n',
        '#include "'+str(project/'src/runtime/pes13_perf37_probe.h')+'"\n'
        'extern int wine_nx_box64_sample_detail(uintptr_t, struct pes37_sample *) __attribute__((weak));\n'
        'struct nx_prof_target\n')
    text=once(text,'    struct nx_prof_table tables[NX_PROF_TABLES];',
        '    struct nx_prof_table tables[NX_PROF_TABLES];\n    struct pes37_hist jit;')
    text=once(text,'            ThreadContext ctx;',
        '            ThreadContext ctx;\n            struct pes37_sample detail={0};')
    text=once(text,'                if (&wine_nx_box64_pc_to_x86) translated = wine_nx_box64_pc_to_x86( ctx.pc.x, &x86 );',
        '                if (&wine_nx_box64_sample_detail && wine_nx_box64_sample_detail(ctx.pc.x,&detail)) {\n'
        '                    translated=1; x86=detail.guest_pc;\n'
        '                } else if (&wine_nx_box64_pc_to_x86) translated = wine_nx_box64_pc_to_x86( ctx.pc.x, &x86 );')
    text=once(text,'            if (R_SUCCEEDED( rc )) record( target, &ctx, translated, x86, callers, count, x86_callers, x86_count );',
        '            if (R_SUCCEEDED( rc )) {\n'
        '                record(target,&ctx,translated,x86,callers,count,x86_callers,x86_count);\n'
        '                pes37_add(&target->jit,&detail);\n            }')
    text=once(text,'        if (target->kinds[NX_PROF_X86]) report_modules( target, line );',
        '        if (target->kinds[NX_PROF_X86]) report_modules( target, line );\n'
        '        pes37_report(target->tid,target->kind,&target->jit,wine_nx_runtime_trace);')
    return text
