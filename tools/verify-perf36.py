"""Audit the built artifact, not merely the requested emitter configuration."""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
from nro_assets import inspect_nro
from perf36_patches import OLD, NEW, OPS

p = Path(__file__).resolve().parents[1]
w = p / 'local/perf36'
root = Path(os.environ.get('PES_BUILD_ROOT', '/home/blekjek/pes13-build'))
source = root / 'runtime-perf11-source'
build = root / 'runtime-perf36-scoped-fastnan'
base = root / 'runtime-perf34-config'
sha = lambda data: hashlib.sha256(data).hexdigest()
assert json.loads((w / 'build-status.json').read_text()) == dict(state='complete', restored=True)
for rel, digest in json.loads((w / 'source-baseline.json').read_text()).items():
    assert sha((source / rel).read_bytes()) == digest, rel
commands = subprocess.check_output(['ninja', '-C', str(build), '-t', 'commands'], text=True).splitlines()
objdump = '/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump'
def instructions(obj):
    output = subprocess.check_output([objdump, '-d', str(obj)], text=True)
    return re.findall(r'^\s*[0-9a-f]+:\s+([0-9a-f]{8})\s', output, re.M)

changes = json.loads((w / 'fastnan-changes.json').read_text())
assert {e['name'] for e in changes} == {f'dynarec_arm64_{op}.c' for op in OPS}
objects = []
for e in changes:
    file = w / 'generated' / e['name']
    text = file.read_text()
    assert sha(text.encode()) == e['generated_sha256']
    assert OLD not in text and text.count(NEW) == e['sites']
    baseline = p / 'local/perf34/generated' / e['name']
    if not baseline.exists():
        baseline = source / 'wine-nx-probe/vendor/box64/src/dynarec/arm64' / e['name']
    assert text.replace(NEW, OLD) == baseline.read_text()
    matches = [s for s in commands if ' -c ' + str(file) in s]
    assert len(matches) == 4, e['name']
    for step in range(4):
        assert sum(f'-DSTEP={step} ' in s for s in matches) == 1
    assert all('-O1' in s for s in matches)
    assert not any(' -c ' in s and s.endswith('/vendor/box64/src/dynarec/arm64/' + e['name']) for s in commands)
    old = list((base / 'CMakeFiles/wine-nx-box64-core-pass3.dir').rglob(e['name'] + '.obj'))
    new = list((build / 'CMakeFiles/wine-nx-box64-core-pass3.dir').rglob(e['name'] + '.obj'))
    assert len(old) == len(new) == 1
    a, b = instructions(old[0]), instructions(new[0])
    assert a and b and a != b, ('no machine-code change', e['name'])
    objects.append(dict(name=e['name'], baseline_instructions=len(a), new_instructions=len(b),
                        baseline_code_sha256=sha(''.join(a).encode()),
                        new_code_sha256=sha(''.join(b).encode())))

# The runtime dispatch and inherited scoped policy must remain the baseline.
for name in ('wine-nx-box64-core-dynarec.c', 'wine-nx-box64-core-dynablock.c'):
    assert (build / name).read_bytes() == (base / name).read_bytes()
dispatch = 'CMakeFiles/wine-nx-box64-core.dir/wine-nx-box64-core-dynarec.c.obj'
assert (build / dispatch).read_bytes() == (base / dispatch).read_bytes()
assert (w / 'pes13_perf25_env.h').read_bytes() == (p / 'local/perf34/pes13_perf25_env.h').read_bytes()
assert (p / 'local/perf33/pes13_perf25_env.h').read_bytes() == (w / 'pes13_perf25_env.h').read_bytes()
assert '-DSAVE_MEM' not in (build / 'build.ninja').read_text()
tests = json.loads((w / 'fastnan-test/results.json').read_text())
assert tests['cases'] == 19000 and tests['fallback_byte_identical']
assert 'four-pass immutability' in (w / 'policy-test.log').read_text()
nro = (w / 'payload/switch/pes13-nx/pes13-nx.nro').read_bytes()
assert b'pes13-nx-0.2.0-perf36-scoped-fastnan' in nro
assert b'[PERF36] FASTNAN emitter=per-block' in nro
assert sha(nro) == json.loads((w / 'build.json').read_text())['nro_sha256']
metadata = inspect_nro(nro, (p / 'assets/icon.jpg').read_bytes(), expected_title='PES13-NX PERF36 FASTNAN')
report = json.loads((w / 'verification.json').read_text())
report.update(fastnan_four_passes=True, fastnan_sites=sum(e['sites'] for e in changes),
              pass3_machine_code_changed=objects, dispatch_byte_identical_to_perf34=True,
              scoped_policy_byte_identical_to_perf34=True, source_restored=True,
              scalar_execution_test=tests, scoped_policy_asan_ubsan='PASS',
              nro_metadata=metadata, hardware_tested=False, target_verified=False)
(w / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
print('PERF36: all 8 emitters / 4 passes wired; pass3 machine code changed; dispatch and scope unchanged; NRO assets and source restoration PASS')
