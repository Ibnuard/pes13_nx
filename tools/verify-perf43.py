"""Verify PERF43 changes only diagnostics relative to PERF42."""
from pathlib import Path
import hashlib
import json
import os
import subprocess

from nro_assets import inspect_nro

project = Path(__file__).resolve().parents[1]
work = project / 'local/perf43'
root = Path(os.environ.get('PES_BUILD_ROOT', '/home/blekjek/pes13-build'))
source = root / 'runtime-perf11-source'
build = root / 'runtime-perf43-match-probe'
baseline = root / 'runtime-perf42-startup-guard'
sha = lambda data: hashlib.sha256(data).hexdigest()

assert json.loads((work / 'build-status.json').read_text()) == {
    'state': 'complete', 'restored': True}
for name, digest in json.loads((work / 'source-baseline.json').read_text()).items():
    assert sha((source / name).read_bytes()) == digest, name

emitters = sorted((work / 'generated').glob('*.c'))
assert len(emitters) == 14
for file in emitters:
    assert file.read_bytes() == (project / 'local/perf42/generated' / file.name).read_bytes(), file.name
for name in ('wine-nx-box64-core-dynablock.c',
             'wine-nx-box64-core-dynarec_native.c'):
    assert (build / name).read_bytes() == (baseline / name).read_bytes(), name

for name in ('pes13_perf21_capture.h', 'pes13_perf20_capture.h'):
    newer = (work / name).read_text().replace('perf43', 'perf42')
    older = (project / 'local/perf42' / name).read_text()
    assert newer == older, name

guard = (work / 'wow64_box64_unix.c').read_text()
assert guard.count('pes42_after_run( status, p )') == 1

fixture = root / 'perf43-jit-histogram-test'
subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', str(project / 'tests/perf37_probe.c'),
                '-o', str(fixture)], check=True)
output = subprocess.check_output([str(fixture)], text=True)
assert 'output bounds PASS' in output

symbols = subprocess.check_output([
    '/opt/devkitpro/devkitA64/bin/aarch64-none-elf-nm',
    str(build / 'wine-nx-runtime.elf')], text=True)
assert ' wine_nx_box64_sample_detail\n' in symbols
assert ' wine_nx_perf42_guard_enabled\n' in symbols

nro = (work / 'payload/switch/pes13-nx/pes13-nx.nro').read_bytes()
for marker in (b'pes13-nx-0.2.0-perf43-match-probe', b'[JIT37-BLOCK]',
               b'[JIT37-WORDS]', b'[BOOT42]', b'[PERF43]'):
    assert marker in nro, marker
assert sha(nro) == json.loads((work / 'build.json').read_text())['nro_sha256']
metadata = inspect_nro(nro, (project / 'assets/icon.jpg').read_bytes(),
                       expected_title='PES13-NX PERF43 MATCH PROBE')

report = json.loads((work / 'verification.json').read_text())
report.update(base='PERF42', source_restored=True,
              emitter_sources_identical_to_perf42=[file.name for file in emitters],
              native_pass_source_identical_to_perf42=True,
              startup_guard_retained=True, jit_probe_linked=True,
              probe_asan_ubsan='PASS', nro_metadata=metadata,
              hardware_tested=False, target_verified=False,
              performance_improvement_claimed=False,
              changed_source_sha256={
                  str(file.relative_to(project)): sha(file.read_bytes()) for file in (
                      project / 'tools/perf43_patches.py',
                      project / 'tools/build-perf43.py',
                      project / 'tools/run-perf43-build.py',
                      project / 'tools/verify-perf43.py',
                  )})
(work / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
print('PERF43: execution emitters/native pass unchanged, JIT probe linked, '
      'startup guard retained, NRO/source restoration PASS')
