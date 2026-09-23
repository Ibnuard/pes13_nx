"""Verify the fingerprinted matrix sibling and unchanged PERF40 baseline."""
from pathlib import Path
import hashlib
import json
import os
import subprocess

from nro_assets import inspect_nro

project = Path(__file__).resolve().parents[1]
work = project / 'local/perf41'
root = Path(os.environ.get('PES_BUILD_ROOT', '/home/blekjek/pes13-build'))
source = root / 'runtime-perf11-source'
build = root / 'runtime-perf41-matrix-round'
baseline = root / 'runtime-perf40-early-round'
sha = lambda data: hashlib.sha256(data).hexdigest()

assert json.loads((work / 'build-status.json').read_text()) == {
    'state': 'complete', 'restored': True}
for name, digest in json.loads((work / 'source-baseline.json').read_text()).items():
    assert sha((source / name).read_bytes()) == digest, name

capture_root = project / 'local/perf39/results/447687a6efc4/all-captures'
for slot, length, digest in (
    (6, 1113, 'a0a440c231cde7d30387d12ac94725615ba0cd52f6107f448cd16f61637619f6'),
    (7, 232, '737c8648db2f5c80f282d7c13bd3696a6c35e0d970c0f0b72c603e370b8e89d2'),
):
    guest = (capture_root / f'slot-{slot}-x86.bin').read_bytes()
    assert len(guest) == length and sha(guest) == digest

header = (work / 'pes13_perf21_capture.h').read_text()
assert header.count('pes40_match_early(addr)') == 1
assert header.count('pes41_match_matrix(addr)') == 1
assert header.count('wine_nx_perf20_capture(opaque)') == 2
assert 'if (!pes41_matrix && (!pes40_mode || !pes40_match_early(addr)))' in header
assert 'if (start == PES41_MATRIX_ADDR && pes41_mode)' in header
assert 'wine_nx_perf40_report' in header and 'wine_nx_perf41_report' in header
for name in ('wine-nx-box64-core-dynarec.c',
             'wine-nx-box64-core-dynablock.c',
             'wine-nx-box64-core-dynarec_native.c'):
    assert (build / name).read_bytes() == (baseline / name).read_bytes(), name
emitters = sorted((work / 'generated').glob('*.c'))
assert len(emitters) == 14
for file in emitters:
    assert file.read_bytes() == (project / 'local/perf40/generated' / file.name).read_bytes()

test = root / 'perf41-policy-test'
subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', str(project / 'tests/perf41_policy.c'),
                '-o', str(test)], check=True)
subprocess.run([str(test), str(capture_root / 'slot-6-x86.bin'),
                str(capture_root / 'slot-7-x86.bin')], check=True)

symbols = subprocess.check_output([
    '/opt/devkitpro/devkitA64/bin/aarch64-none-elf-nm',
    str(build / 'wine-nx-runtime.elf')], text=True)
for symbol in (' wine_nx_perf20_capture\n', ' wine_nx_perf33_completed\n',
               ' wine_nx_perf38_report\n', ' wine_nx_perf40_report\n',
               ' wine_nx_perf41_report\n'):
    assert symbol in symbols, symbol

nro = (work / 'payload/switch/pes13-nx/pes13-nx.nro').read_bytes()
assert b'pes13-nx-0.2.0-perf41-matrix-round' in nro
assert b'[PERF41]' in nro and b'[PERF40]' in nro
assert sha(nro) == json.loads((work / 'build.json').read_text())['nro_sha256']
metadata = inspect_nro(nro, (project / 'assets/icon.jpg').read_bytes(),
                       expected_title='PES13-NX PERF41 MATRIXROUND')

report = json.loads((work / 'verification.json').read_text())
report.update({
    'base': 'PERF40', 'source_restored': True,
    'matrix_policy_host_test': 'PASS',
    'native_pass_source_identical_to_perf40': True,
    'emitter_sources_identical_to_perf40': [file.name for file in emitters],
    'nro_metadata': metadata,
    'hardware_tested': False,
    'performance_improvement_claimed': False,
    'target_verified': False,
    'changed_source_sha256': {
        str(file.relative_to(project)): sha(file.read_bytes()) for file in (
            project / 'src/runtime/pes13_perf41.h',
            project / 'tools/perf41_patches.py',
            project / 'tools/build-perf41.py',
            project / 'tools/run-perf41-build.py',
            project / 'tools/verify-perf41.py',
            project / 'tests/perf41_policy.c',
        )},
})
(work / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
print('PERF41 fingerprint, matrix/PERF19 boundary, NRO/source restoration PASS')
