"""Verify the narrow guard, unchanged native math emitters, and restored WSL sources."""
from pathlib import Path
import hashlib
import json
import os
import subprocess

from nro_assets import inspect_nro

project = Path(__file__).resolve().parents[1]
work = project / 'local/perf42'
root = Path(os.environ.get('PES_BUILD_ROOT', '/home/blekjek/pes13-build'))
source = root / 'runtime-perf11-source'
build = root / 'runtime-perf42-startup-guard'
baseline = root / 'runtime-perf40-early-round'
sha = lambda data: hashlib.sha256(data).hexdigest()

assert json.loads((work / 'build-status.json').read_text()) == {
    'state': 'complete', 'restored': True}
for name, digest in json.loads((work / 'source-baseline.json').read_text()).items():
    assert sha((source / name).read_bytes()) == digest, name

unix = (work / 'wow64_box64_unix.c').read_text()
assert unix.count('pes42_after_run( status, p )') == 1
assert unix.count('wine_nx_box64_last_fault(') == 1
assert unix.count('STATUS_TIMEOUT;') == 1
assert 'pes28_after_run' not in unix

for name in ('wine-nx-box64-core-dynarec.c',
             'wine-nx-box64-core-dynablock.c',
             'wine-nx-box64-core-dynarec_native.c'):
    assert (build / name).read_bytes() == (baseline / name).read_bytes(), name
emitters = sorted((work / 'generated').glob('*.c'))
assert len(emitters) == 14
for file in emitters:
    assert file.read_bytes() == (project / 'local/perf40/generated' / file.name).read_bytes()

test = root / 'perf42-guard-test'
subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', str(project / 'tests/perf42_guard.c'),
                '-o', str(test)], check=True)
subprocess.run([str(test), str(project / 'local/perf29/results/decoded-prev1/caller-0115c300.bin'),
                str(project / 'local/perf29/results/decoded-prev1/stack-0219fca4.bin')], check=True)

symbols = subprocess.check_output([
    '/opt/devkitpro/devkitA64/bin/aarch64-none-elf-nm',
    str(build / 'wine-nx-runtime.elf')], text=True)
for symbol in (' wine_nx_perf42_guard_enabled\n', ' wine_nx_perf42_identity\n',
               ' wine_nx_perf40_report\n'):
    assert symbol in symbols, symbol
nro = (work / 'payload/switch/pes13-nx/pes13-nx.nro').read_bytes()
assert b'pes13-nx-0.2.0-perf42-startup-guard' in nro
assert b'[BOOT42]' in nro and b'[PERF40]' in nro and b'[PERF41]' not in nro
assert sha(nro) == json.loads((work / 'build.json').read_text())['nro_sha256']
metadata = inspect_nro(nro, (project / 'assets/icon.jpg').read_bytes(),
                       expected_title='PES13-NX PERF42 BOOTGUARD')
report = json.loads((work / 'verification.json').read_text())
report.update(base='PERF40', source_restored=True,
              startup_guard_fixture='PASS',
              native_pass_source_identical_to_perf40=True,
              emitter_sources_identical_to_perf40=[file.name for file in emitters],
              nro_metadata=metadata, hardware_tested=False,
              target_verified=False, performance_improvement_claimed=False,
              changed_source_sha256={
                  str(file.relative_to(project)): sha(file.read_bytes()) for file in (
                      project / 'src/runtime/pes13_perf42_guard.h',
                      project / 'src/runtime/pes13_perf42_unix.h',
                      project / 'tools/perf42_patches.py',
                      project / 'tools/build-perf42.py',
                      project / 'tools/run-perf42-build.py',
                      project / 'tools/verify-perf42.py',
                      project / 'tests/perf42_guard.c',
                  )})
(work / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
print('PERF42 captured fault guard, unchanged native math source, NRO/source restoration PASS')
