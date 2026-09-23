"""Wire PERF33's existing FASTNAN override into the ARM64 opcode emitters."""
from pathlib import Path
import hashlib
import json
import os
import perf34_patches
from perf17_patches import once

adapt_profile = perf34_patches.adapt_profile
OPS = ('0f', '660f', 'avx_0f', 'avx_66_0f', 'avx_f2_0f',
       'avx_f3_0f', 'f20f', 'f30f')
OLD = 'BOX64ENV(dynarec_fastnan)'
NEW = 'BOX64DRENV(dynarec_fastnan)'


def wire_emitters(cmake, project):
    root = Path(os.environ.get('PES_BUILD_ROOT', '/home/blekjek/pes13-build'))
    arm = root / 'runtime-perf11-source/wine-nx-probe/vendor/box64/src/dynarec/arm64'
    work = project / 'local/perf36'
    output = work / 'generated'
    output.mkdir(parents=True, exist_ok=True)
    found = {p.name for p in arm.glob('*.c') if OLD in p.read_text()}
    assert found == {f'dynarec_arm64_{op}.c' for op in OPS}, found
    changes = []
    for name in sorted(found):
        generated = output / name
        # Seven files already contain PERF22's FASTROUND/X87DOUBLE changes.
        # The AVX 0F emitter is the only extra source in this experiment.
        already_generated = name != 'dynarec_arm64_avx_0f.c'
        original = generated.read_text() if already_generated else (arm / name).read_text()
        assert OLD in original and NEW not in original, name
        changed = original.replace(OLD, NEW)
        assert changed.replace(NEW, OLD) == original
        generated.write_text(changed)
        if not already_generated:
            assert name == 'dynarec_arm64_avx_0f.c'
            anchor = '    list(TRANSFORM pass_sources PREPEND "${root}/src/dynarec/arm64/")'
            extra = ('\n    list(REMOVE_ITEM pass_sources "${root}/src/dynarec/arm64/' + name + '")'
                     '\n    list(APPEND pass_sources "' + str(generated) + '")')
            cmake = once(cmake, anchor, anchor + extra)
        changes.append(dict(name=name, sites=original.count(OLD),
                            original_sha256=hashlib.sha256(original.encode()).hexdigest(),
                            generated_sha256=hashlib.sha256(changed.encode()).hexdigest()))
    (work / 'fastnan-changes.json').write_text(json.dumps(changes, indent=2) + '\n')
    return cmake


def adapt(cmake, dynarec, runtime, project):
    # Keep historical generated headers immutable.
    path = project / 'tools/perf34_patches.py'
    ns = {'__file__': str(path), '__name__': 'perf36_base34'}
    exec(compile(path.read_text().replace('local/perf34', 'local/perf36'), str(path), 'exec'), ns)
    cmake, dynarec, runtime = ns['adapt'](cmake, dynarec, runtime, project)
    cmake = wire_emitters(cmake, project)
    runtime = runtime.replace('pes13-nx-0.2.0-perf34-config', 'pes13-nx-0.2.0-perf36-scoped-fastnan')
    runtime = once(runtime, '    wine_nx_thread_report();',
        '    { static int reported; if (!reported) { reported=1;\n'
        '      log_line("[PERF36] FASTNAN emitter=per-block; scope=PERF33; global preset unchanged"); } }\n'
        '    wine_nx_thread_report();')
    return cmake, dynarec, runtime


def adapt_recipe(text):
    text = perf34_patches.adapt_recipe(text)
    for old, new in [('runtime-perf34-config', 'runtime-perf36-scoped-fastnan'),
                     ('pes13-nx-0.2.0-perf34-config', 'pes13-nx-0.2.0-perf36-scoped-fastnan'),
                     ('PES13-NX PERF34 CONFIG', 'PES13-NX PERF36 FASTNAN'),
                     ('local/perf34', 'local/perf36')]:
        text = text.replace(old, new)
    return text
