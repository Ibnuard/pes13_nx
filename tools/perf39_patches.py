"""PERF38 gameplay with successful-block capture for fallback environments."""
from pathlib import Path

from perf17_patches import once
import perf38_patches

adapt_profile = perf38_patches.adapt_profile


def base38(project):
    path = project / 'tools/perf38_patches.py'
    source = path.read_text()
    for old, new in (
        ('local/perf38', 'local/perf39'),
        ('runtime-perf38-region-fusion', 'runtime-perf39-capture-repair'),
        ('pes13-nx-0.2.0-perf38-region-fusion', 'pes13-nx-0.2.0-perf39-capture-repair'),
        ('PES13-NX PERF38 FUSION', 'PES13-NX PERF39 CAPTURE'),
    ):
        source = source.replace(old, new)
    namespace = {'__file__': str(path), '__name__': 'perf39_base38'}
    exec(compile(source, str(path), 'exec'), namespace)
    return namespace


def adapt(cmake, dynarec, runtime, project):
    cmake, dynarec, runtime = base38(project)['adapt'](cmake, dynarec, runtime, project)
    original = project / 'src/runtime/pes13_perf21.h'
    generated = project / 'local/perf39/pes13_perf21_capture.h'
    # PERF21's old predicate omitted blocks translated with box64env while
    # pes21_mode was enabled: boot blocks and the excluded matrix page. The
    # capture helper itself checks the opt-in flag, image, and exact address.
    header = once(original.read_text(),
                  '    } else if (!pes21_mode) {\n        wine_nx_perf20_capture(opaque);',
                  '    } else {\n        wine_nx_perf20_capture(opaque);')
    generated.write_text(header)
    dynarec = once(dynarec, '#include "' + str(original) + '"',
                   '#include "' + str(generated) + '"')
    return cmake, dynarec, runtime


def adapt_recipe(source):
    return base38(Path(__file__).resolve().parents[1])['adapt_recipe'](source)
