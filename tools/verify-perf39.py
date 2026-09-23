"""Verify PERF39 changes only completed-block diagnostic capture."""
from pathlib import Path
import hashlib
import json
import os
import subprocess

from nro_assets import inspect_nro

project = Path(__file__).resolve().parents[1]
work = project / 'local/perf39'
root = Path(os.environ.get('PES_BUILD_ROOT', '/home/blekjek/pes13-build'))
source = root / 'runtime-perf11-source'
build = root / 'runtime-perf39-capture-repair'
baseline = root / 'runtime-perf38-region-fusion'
sha = lambda data: hashlib.sha256(data).hexdigest()

assert json.loads((work / 'build-status.json').read_text()) == {
    'state': 'complete', 'restored': True}
for name, digest in json.loads((work / 'source-baseline.json').read_text()).items():
    assert sha((source / name).read_bytes()) == digest, name

original = (project / 'src/runtime/pes13_perf21.h').read_text()
generated = (work / 'pes13_perf21_capture.h').read_text()
assert original.count('} else if (!pes21_mode) {') == 1
assert generated.replace('} else {\n        wine_nx_perf20_capture(opaque);',
                         '} else if (!pes21_mode) {\n        wine_nx_perf20_capture(opaque);') == original
for name in ('wine-nx-box64-core-dynarec.c',
             'wine-nx-box64-core-dynablock.c',
             'wine-nx-box64-core-dynarec_native.c'):
    assert (build / name).read_bytes() == (baseline / name).read_bytes(), name
emitters = sorted((work / 'generated').glob('*.c'))
assert len(emitters) == 14
for file in emitters:
    assert file.read_bytes() == (project / 'local/perf38/generated' / file.name).read_bytes()

test = root / 'perf39-capture-test'
subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', str(project / 'tests/perf39_capture.c'),
                '-o', str(test)], check=True)
subprocess.run([str(test)], check=True)

symbols = subprocess.check_output([
    '/opt/devkitpro/devkitA64/bin/aarch64-none-elf-nm',
    str(build / 'wine-nx-runtime.elf')], text=True)
assert ' wine_nx_perf20_capture\n' in symbols
assert ' wine_nx_perf33_completed\n' in symbols
assert ' wine_nx_perf38_report\n' in symbols
nro = (work / 'payload/switch/pes13-nx/pes13-nx.nro').read_bytes()
assert b'pes13-nx-0.2.0-perf39-capture-repair' in nro
assert b'[PERF38]' in nro
assert sha(nro) == json.loads((work / 'build.json').read_text())['nro_sha256']
metadata = inspect_nro(nro, (project / 'assets/icon.jpg').read_bytes(),
                       expected_title='PES13-NX PERF39 CAPTURE')

report = json.loads((work / 'verification.json').read_text())
report.update({
    'base': 'PERF38', 'source_restored': True,
    'capture_host_test': 'PASS',
    'native_pass_source_identical_to_perf38': True,
    'emitter_sources_identical_to_perf38': [file.name for file in emitters],
    'gameplay_policy_changed': False,
    'nro_metadata': metadata,
    'hardware_tested': False,
    'performance_improvement_claimed': False,
    'target_verified': False,
    'changed_source_sha256': {
        str(file.relative_to(project)): sha(file.read_bytes()) for file in (
            project / 'tools/perf39_patches.py',
            project / 'tools/build-perf39.py',
            project / 'tools/run-perf39-build.py',
            project / 'tools/verify-perf39.py',
            project / 'tests/perf39_capture.c',
        )},
})
(work / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
print('PERF39 capture host test, native pass/emitters, NRO metadata, source restoration PASS')
