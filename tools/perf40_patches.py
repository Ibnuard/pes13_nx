"""PERF39 gameplay plus fingerprinted early FASTROUND for one math block."""
from pathlib import Path

from perf17_patches import once
import perf39_patches

adapt_profile = perf39_patches.adapt_profile


def base39(project):
    path = project / 'tools/perf39_patches.py'
    source = path.read_text()
    for old, new in (
        ('local/perf39', 'local/perf40'),
        ('runtime-perf39-capture-repair', 'runtime-perf40-early-round'),
        ('pes13-nx-0.2.0-perf39-capture-repair', 'pes13-nx-0.2.0-perf40-early-round'),
        ('PES13-NX PERF39 CAPTURE', 'PES13-NX PERF40 EARLYROUND'),
    ):
        source = source.replace(old, new)
    namespace = {'__file__': str(path), '__name__': 'perf40_base39'}
    exec(compile(source, str(path), 'exec'), namespace)
    return namespace


def adapt(cmake, dynarec, runtime, project):
    cmake, dynarec, runtime = base39(project)['adapt'](cmake, dynarec, runtime, project)
    header = project / 'local/perf40/pes13_perf21_capture.h'
    source = header.read_text()
    policy = project / 'src/runtime/pes13_perf40.h'
    source = once(source, 'static int pes21_mode;',
                  '#include "' + str(policy) + '"\n'
                  'static int pes40_mode;\n'
                  'static unsigned int pes40_early_selected, pes40_early_rejected;\n'
                  'static int pes21_mode;')
    source = once(source,
        '''    if (!__atomic_load_n(&wine_nx_vk_successful_presents, __ATOMIC_ACQUIRE)) {
        __atomic_add_fetch(&pes21_boot_fallback, 1, __ATOMIC_RELAXED);
        return &box64env;
    }''',
        '''    if (!__atomic_load_n(&wine_nx_vk_successful_presents, __ATOMIC_ACQUIRE)) {
        /* A measured pre-present math block is the sole exception. The
         * pinned matrix page, packer, DLLs and every other boot block keep
         * their established Compatible environment. */
        if (!pes40_mode || !pes40_match_early(addr)) {
            if (pes40_mode && addr == PES40_EARLY_ADDR)
                __atomic_add_fetch(&pes40_early_rejected, 1, __ATOMIC_RELAXED);
            __atomic_add_fetch(&pes21_boot_fallback, 1, __ATOMIC_RELAXED);
            return &box64env;
        }
        __atomic_add_fetch(&pes40_early_selected, 1, __ATOMIC_RELAXED);
    }''')
    assert source.endswith('#endif\n')
    source = source[:-len('#endif\n')] + '''
void wine_nx_perf40_report(void)
{
    char line[192];
    snprintf(line, sizeof(line),
        "[PERF40] early_round=%d target=0113027b selected=%u fingerprint_rejected=%u; translations, not executions",
        pes40_mode,
        __atomic_load_n(&pes40_early_selected, __ATOMIC_RELAXED),
        __atomic_load_n(&pes40_early_rejected, __ATOMIC_RELAXED));
    if (&wine_nx_runtime_trace) wine_nx_runtime_trace(line);
}
#endif
'''
    header.write_text(source)
    dynarec = once(dynarec, '    apply_box64_options();',
        '    apply_box64_options();\n'
        '    pes40_mode = wine_nx_config_file_bool(\n'
        '        "sdmc:/switch/pes13-nx/perf40-early-round.txt", 0);')
    runtime = once(runtime, '    wine_nx_thread_report();',
        '    { extern void wine_nx_perf40_report(void); wine_nx_perf40_report(); }\n'
        '    wine_nx_thread_report();')
    return cmake, dynarec, runtime


def adapt_recipe(source):
    return base39(Path(__file__).resolve().parents[1])['adapt_recipe'](source)
