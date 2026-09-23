"""PERF42 execution policy with bounded JIT sampling for the match slowdown."""
from pathlib import Path

from perf17_patches import once
import perf37_patches


def base42(project):
    path = project / 'tools/perf42_patches.py'
    source = path.read_text()
    for old, new in (
        ('local/perf42', 'local/perf43'),
        ('runtime-perf42-startup-guard', 'runtime-perf43-match-probe'),
        ('pes13-nx-0.2.0-perf42-startup-guard', 'pes13-nx-0.2.0-perf43-match-probe'),
        ('PES13-NX PERF42 BOOTGUARD', 'PES13-NX PERF43 MATCH PROBE'),
    ):
        assert old in source, old
        source = source.replace(old, new)
    namespace = {'__file__': str(path), '__name__': 'perf43_base42'}
    exec(compile(source, str(path), 'exec'), namespace)
    return namespace


def adapt(cmake, dynarec, runtime, project):
    cmake, dynarec, runtime = base42(project)['adapt'](
        cmake, dynarec, runtime, project)
    anchor = 'int wine_nx_box64_pc_to_x86( uintptr_t pc, uintptr_t *x86 )'
    includes = ''.join('#include "' + str(project / 'src/runtime' / name) + '"\n'
                       for name in ('pes13_perf37_probe.h', 'pes13_perf37_sample.h'))
    dynarec = once(dynarec, anchor, includes + anchor)
    runtime = once(runtime, '    wine_nx_thread_report();',
                   '    { static int reported; if (!reported) { reported=1;\n'
                   '      log_line("[PERF43] match JIT sampler; PERF42 execution policy retained"); } }\n'
                   '    wine_nx_thread_report();')
    return cmake, dynarec, runtime


def adapt_recipe(source):
    return base42(Path(__file__).resolve().parents[1])['adapt_recipe'](source)


def adapt_profile(source, project):
    return perf37_patches.adapt_profile(source, project)
