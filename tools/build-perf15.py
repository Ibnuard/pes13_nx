"""WSL: build matched NRO/ARM64 PE exception ABI; restore all baseline sources."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from perf15_patches import source_changes, apply_hunks

p = Path(__file__).resolve().parents[1]
root = Path(os.environ.get('PES_BUILD_ROOT', str(Path.home()/'.cache/pes13-nx')))
runtime = root/'runtime-perf11-source'
pe_source = root/'source'
dest = p/'local/perf15'
payload = dest/'payload/switch/pes13-nx'
payload.mkdir(parents=True, exist_ok=True)
compiler = root/'toolchains/llvm-mingw-20260505-ucrt-ubuntu-22.04-x86_64/bin'
env = dict(os.environ)
env['PATH'] = f'{compiler}:/opt/devkitpro/devkitA64/bin:/opt/devkitpro/tools/bin:/usr/bin:/bin'
env['CC'] = '/usr/bin/cc'
changes = source_changes(runtime, p/'patches/perf15')
for rel in ('dlls/winebox64/cpu.c', 'dlls/winebox64/unixlib.h',
            'wine-nx-probe/source/wow64_box64_bridge.c', 'wine-nx-probe/source/wow64_box64_bridge.h'):
    patch = (p/'patches/perf15'/(rel.replace('/','_')+'.patch')).read_text()
    changes[pe_source/rel] = apply_hunks((pe_source/rel).read_text(), patch)
originals = {path: path.read_bytes() for path in changes}
pe_dir = root/'pe/dlls/winebox64/aarch64-windows'
pe_files = {path: path.read_bytes() for path in pe_dir.iterdir() if path.is_file()}
sha = lambda b: hashlib.sha256(b).hexdigest()

try:
    for path, text in changes.items():
        path.write_text(text)
    subprocess.run([sys.executable, str(p/'tests/perf15_exceptions.py'), str(runtime)], env=env, check=True)
    for test in ('check-wow64-box64-bridge.sh', 'check-wow64-box64-unix.sh'):
        subprocess.run(['sh', str(runtime/'wine-nx-probe'/test)], env=env, check=True)
    if '--check' not in sys.argv:
        subprocess.run(['make', '-C', str(root/'pe'), '-j4',
            'dlls/winebox64/aarch64-windows/winebox64.dll'], env=env, check=True)
        target = payload/'drive_c/windows/system32/winebox64.dll'
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pe_dir/'winebox64.dll', target)
        # Keep original driver and tests unchanged; compose PERF14 guards with
        # the already patched exception sources, in a separate build directory.
        driver = (p/'tools/build-perf11-runtime.py').read_text()
        anchor = "\nexec(compile(recipe, str(recipe_path), 'exec'), {'__file__': str(recipe_path), '__name__': '__main__'})"
        assert driver.count(anchor) == 1
        extension = '''
from perf14_build import adapt_recipe
recipe = adapt_recipe(recipe)
recipe = recipe.replace('runtime-perf14-map-guards', 'runtime-perf15-guest-exceptions')
recipe = recipe.replace('pes13-nx-0.2.0-perf14-map-guards', 'pes13-nx-0.2.0-perf15-guest-exceptions')
recipe = recipe.replace('PES13-NX PERF14', 'PES13-NX PERF15')
recipe = recipe.replace('local/perf14', 'local/perf15')
recipe = recipe.replace('PERF14 NRO built', 'PERF15 NRO built')
'''
        driver = driver.replace(anchor, extension+anchor)
        exec(compile(driver, str(p/'tools/build-perf11-runtime.py'), 'exec'),
            {'__file__': str(p/'tools/build-perf11-runtime.py'), '__name__': '__main__'})
finally:
    for path, data in originals.items():
        path.write_bytes(data)
    # Build output only, verified directory inside this explicit PE build root.
    assert pe_dir.resolve().is_relative_to((root/'pe').resolve())
    for path in pe_dir.iterdir():
        if path.is_file() and path not in pe_files:
            path.unlink()
    for path, data in pe_files.items():
        path.write_bytes(data)
    assert all(path.read_bytes() == data for path, data in originals.items())
    assert all(path.read_bytes() == data for path, data in pe_files.items())
    print('PERF15 source/PE baseline restored', flush=True)
if '--check' not in sys.argv:
    (dest/'pair.json').write_text(json.dumps({
        'abi': 4, 'run_params_bytes': 56, 'hardware_tested': False,
        'nro_sha256': sha((payload/'pes13-nx.nro').read_bytes()),
        'dll_sha256': sha((payload/'drive_c/windows/system32/winebox64.dll').read_bytes()),
        'source_restored': True,
    }, indent=2))
