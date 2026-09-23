"""Scope redundant FPCR write elimination to captured arithmetic/store sites."""
from pathlib import Path
from perf17_patches import once


def source_changes(root, project):
    arm = root / 'wine-nx-probe/vendor/box64/src/dynarec/arm64'
    changes = {}
    for op in ('d8', 'de', 'd9'):
        path = arm / f'dynarec_arm64_{op}.c'
        text = path.read_text()
        if op == 'd9':
            start = text.index('INST_NAME("FST float[ED], ST0")')
            end = text.index('INST_NAME("FLDENV Ed")', start)
        else:
            start, end = 0, len(text)
        part = text[start:end]
        assert part.count('x87_setround(') == part.count('x87_restoreround(') > 0
        # The token is used only as the argument to its paired restore.
        import re
        pairs = re.findall(r'u8 = x87_setround\([^;]+;(.*?)x87_restoreround\(dyn, ninst, u8\);', part, re.S)
        assert len(pairs) == part.count('x87_setround(')
        for middle in pairs:
            assert not re.search(r'\bu8\b|\bCALL_\w*\s*\(', middle), middle
        part = part.replace('x87_setround(', 'pes18_setround(').replace('x87_restoreround(', 'pes18_restoreround(')
        text = text[:start] + part + text[end:]
        text = once(text, '#include "dynarec_arm64_functions.h"',
                    '#include "dynarec_arm64_functions.h"\n#include "' +
                    str(project / 'src/runtime/pes13_perf18_round.h') + '"')
        changes[path] = text
    return changes


def adapt_cmake(cmake, project):
    hook = '    list(TRANSFORM pass_sources PREPEND "${root}/src/dynarec/arm64/")'
    extra = ''
    for op in ('d8', 'de', 'd9'):
        name = f'dynarec_arm64_{op}.c'
        generated = project / 'local/perf18/generated' / name
        extra += '\n    list(REMOVE_ITEM pass_sources "${root}/src/dynarec/arm64/' + name + '")'
        extra += '\n    list(APPEND pass_sources "' + str(generated) + '")'
    return once(cmake, hook, hook + extra)


def adapt(dynarec, runtime, project):
    anchor = '#include "' + str(project / 'src/runtime/pes13_perf17.h') + '"'
    dynarec = once(dynarec, anchor, anchor + '\n#include "' + str(project / 'src/runtime/pes13_perf18.h') + '"')
    dynarec = once(dynarec, '    apply_box64_options();', '''    apply_box64_options();
    {
        FILE *f = fopen("sdmc:/switch/pes13-nx/perf18-roundguard.txt", "r");
        if (f) { __atomic_store_n(&pes18_mode, fgetc(f) == '1', __ATOMIC_RELEASE); fclose(f); }
    }''')
    runtime = once(runtime, '    wine_nx_thread_report();',
                   '    { extern void wine_nx_perf18_report(void); wine_nx_perf18_report(); }\n    wine_nx_thread_report();')
    return dynarec, runtime
