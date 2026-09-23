"""PERF40 plus fingerprinted FASTROUND for its measured matrix sibling."""
from pathlib import Path

from perf17_patches import once


def base40(project):
    path = project / 'tools/perf40_patches.py'
    source = path.read_text()
    for old, new in (
        ('local/perf40', 'local/perf41'),
        ('runtime-perf40-early-round', 'runtime-perf41-matrix-round'),
        ('pes13-nx-0.2.0-perf40-early-round', 'pes13-nx-0.2.0-perf41-matrix-round'),
        ('PES13-NX PERF40 EARLYROUND', 'PES13-NX PERF41 MATRIXROUND'),
    ):
        source = source.replace(old, new)
    namespace = {'__file__': str(path), '__name__': 'perf41_base40'}
    exec(compile(source, str(path), 'exec'), namespace)
    return namespace


def adapt(cmake, dynarec, runtime, project):
    cmake, dynarec, runtime = base40(project)['adapt'](cmake, dynarec, runtime, project)
    header = project / 'local/perf41/pes13_perf21_capture.h'
    source = header.read_text()
    policy = project / 'src/runtime/pes13_perf41.h'
    source = once(source, 'static int pes40_mode;',
                  '#include "' + str(policy) + '"\n'
                  'static int pes41_mode;\n'
                  'static unsigned int pes41_selected, pes41_early_selected, pes41_rejected;\n'
                  'static int pes40_mode;')
    source = once(source,
        '''    if (!pes21_in_scope(addr)) {
        __atomic_add_fetch(&pes21_scope_fallback, 1, __ATOMIC_RELAXED);
        return &box64env;
    }''',
        '''    int pes41_matrix = 0;
    if (!pes21_in_scope(addr)) {
        if (pes41_mode && addr == PES41_MATRIX_ADDR) {
            pes41_matrix = pes41_match_matrix(addr);
            if (!pes41_matrix)
                __atomic_add_fetch(&pes41_rejected, 1, __ATOMIC_RELAXED);
        }
        if (!pes41_matrix) {
            __atomic_add_fetch(&pes21_scope_fallback, 1, __ATOMIC_RELAXED);
            return &box64env;
        }
    }
    if (pes41_matrix)
        __atomic_add_fetch(&pes41_selected, 1, __ATOMIC_RELAXED);''')
    source = once(source,
                  'if (!pes40_mode || !pes40_match_early(addr)) {',
                  'if (!pes41_matrix && (!pes40_mode || !pes40_match_early(addr))) {')
    source = once(source,
                  '        __atomic_add_fetch(&pes40_early_selected, 1, __ATOMIC_RELAXED);',
                  '''        if (pes41_matrix)
            __atomic_add_fetch(&pes41_early_selected, 1, __ATOMIC_RELAXED);
        else
            __atomic_add_fetch(&pes40_early_selected, 1, __ATOMIC_RELAXED);''')
    source = once(source,
                  '    if (env != &pes21_env || !pes21_in_scope(start)) return end;',
                  '''    if (env != &pes21_env) return end;
    if (start == PES41_MATRIX_ADDR && pes41_mode)
        return end >= PES41_MATRIX_END ? PES41_MATRIX_END-1 : end;
    if (!pes21_in_scope(start)) return end;''')
    assert source.endswith('#endif\n')
    source = source[:-len('#endif\n')] + '''
void wine_nx_perf41_report(void)
{
    char line[192];
    snprintf(line, sizeof(line),
        "[PERF41] matrix_round=%d target=0112f8f0 selected=%u early=%u fingerprint_rejected=%u; translations, not executions",
        pes41_mode,
        __atomic_load_n(&pes41_selected, __ATOMIC_RELAXED),
        __atomic_load_n(&pes41_early_selected, __ATOMIC_RELAXED),
        __atomic_load_n(&pes41_rejected, __ATOMIC_RELAXED));
    if (&wine_nx_runtime_trace) wine_nx_runtime_trace(line);
}
#endif
'''
    header.write_text(source)
    dynarec = once(dynarec, '    apply_box64_options();',
        '    apply_box64_options();\n'
        '    pes41_mode = wine_nx_config_file_bool(\n'
        '        "sdmc:/switch/pes13-nx/perf41-matrix-round.txt", 0);')
    runtime = once(runtime, '    wine_nx_thread_report();',
        '    { extern void wine_nx_perf41_report(void); wine_nx_perf41_report(); }\n'
        '    wine_nx_thread_report();')
    return cmake, dynarec, runtime


def adapt_recipe(source):
    return base40(Path(__file__).resolve().parents[1])['adapt_recipe'](source)


adapt_profile = base40(Path(__file__).resolve().parents[1])['adapt_profile']
