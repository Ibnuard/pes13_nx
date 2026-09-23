"""WSL: stable PERF15 plus the scoped hot-block experiment; restore sources."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
from perf15_patches import source_changes

p = Path(__file__).resolve().parents[1]
root = Path(os.environ.get('PES_BUILD_ROOT', '/home/blekjek/pes13-build'))
runtime = root / 'runtime-perf11-source'
changes = source_changes(runtime, p / 'patches/perf15')
originals = {path: path.read_bytes() for path in changes}
env = dict(os.environ, CC='/usr/bin/cc')
env['PATH'] = '/opt/devkitpro/devkitA64/bin:/opt/devkitpro/tools/bin:' + env['PATH']
with tempfile.TemporaryDirectory(prefix='perf17-test-', dir=root) as tmp:
    exe = str(Path(tmp) / 'policy')
    subprocess.run(['cc', '-O2', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined',
                    '-I' + str(runtime / 'wine-nx-probe/vendor/box64/src/include'),
                    '-I' + str(runtime / 'wine-nx-probe/vendor/box64/src'),
                    str(p / 'tests/perf17_policy.c'), '-o', exe], env=env, check=True)
    subprocess.run([exe, str(p / 'local/game/pes2013.exe')], env=env, check=True)
if '--check' in sys.argv:
    raise SystemExit(0)

try:
    for path, text in changes.items(): path.write_text(text)
    driver = (p / 'tools/build-perf11-runtime.py').read_text()
    anchor = "\nexec(compile(recipe, str(recipe_path), 'exec'), {'__file__': str(recipe_path), '__name__': '__main__'})"
    assert driver.count(anchor) == 1
    extension = '''
from perf14_build import adapt_recipe
recipe = adapt_recipe(recipe)
from perf17_patches import adapt_recipe as adapt_perf17_recipe
recipe = adapt_perf17_recipe(recipe)
'''
    driver = driver.replace(anchor, extension + anchor)
    exec(compile(driver, str(p / 'tools/build-perf11-runtime.py'), 'exec'),
         {'__file__': str(p / 'tools/build-perf11-runtime.py'), '__name__': '__main__'})
finally:
    for path, data in originals.items(): path.write_bytes(data)
    assert all(path.read_bytes() == data for path, data in originals.items())
    print('PERF17 source baseline restored', flush=True)
