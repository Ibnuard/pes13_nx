"""WSL: scoped FPCR write guard on the stable runtime, restoring all inputs."""
from pathlib import Path
import hashlib
import json
import os
import perf17_patches
import perf18_patches

p = Path(__file__).resolve().parents[1]
root = Path(os.environ.get('PES_BUILD_ROOT', '/home/blekjek/pes13-build'))
work = p / 'local/perf18'
work.mkdir(parents=True, exist_ok=True)
tests = json.loads((work / 'round-tests.json').read_text())
assert tests['all_bit_identical'] and tests['cases'] >= 8000
previous_recipe, previous_adapt = perf17_patches.adapt_recipe, perf17_patches.adapt


def recipe(text):
    text = previous_recipe(text)
    for old, new in (('runtime-perf17-hotblocks', 'runtime-perf18-roundguard'),
                     ('pes13-nx-0.2.0-perf17-hotblocks', 'pes13-nx-0.2.0-perf18-roundguard'),
                     ('PES13-NX PERF17', 'PES13-NX PERF18'), ('local/perf17', 'local/perf18')):
        text = text.replace(old, new)
    return text


def adapt(cmake, dynarec, runtime, project):
    cmake, dynarec, runtime = previous_adapt(cmake, dynarec, runtime, project)
    cmake = perf18_patches.adapt_cmake(cmake, project)
    dynarec, runtime = perf18_patches.adapt(dynarec, runtime, project)
    return cmake, dynarec, runtime


perf17_patches.adapt_recipe, perf17_patches.adapt = recipe, adapt
changes = perf18_patches.source_changes(root / 'runtime-perf11-source', p)
originals = {path: path.read_bytes() for path in changes}
before = {str(path): hashlib.sha256(data).hexdigest() for path, data in originals.items()}
(work / 'vendor-before.json').write_text(json.dumps(before, indent=2) + '\n')
try:
    (work / 'generated').mkdir(exist_ok=True)
    for path, text in changes.items(): (work / 'generated' / path.name).write_text(text)
    driver = p / 'tools/build-perf17.py'
    text = driver.read_text().replace('tests/perf17_policy.c', 'tests/perf18_policy.c')
    exec(compile(text, str(driver), 'exec'), {'__file__': str(driver), '__name__': '__main__'})
finally:
    assert all(path.read_bytes() == data for path, data in originals.items())
    (work / 'vendor-restored.json').write_text(json.dumps(before, indent=2) + '\n')
    print('PERF18 vendor sources unchanged byte-for-byte; generated copies used', flush=True)
