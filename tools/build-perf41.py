"""Build PERF41 on the measured, hardware-improved PERF40 configuration."""
from pathlib import Path
import hashlib
import json

project = Path(__file__).resolve().parents[1]
work = project / 'local/perf41'
work.mkdir(parents=True, exist_ok=True)
capture = project / 'local/perf39/results/447687a6efc4/all-captures/slot-7-x86.bin'
assert len(capture.read_bytes()) == 232
assert hashlib.sha256(capture.read_bytes()).hexdigest() == (
    '737c8648db2f5c80f282d7c13bd3696a6c35e0d970c0f0b72c603e370b8e89d2')
assert '0xb04e420af1f912d6' in (
    project / 'src/runtime/pes13_perf41.h').read_text()

path = project / 'tools/build-perf40.py'
source = path.read_text()
for old, new in (
    ('local/perf40', 'local/perf41'),
    ('runtime-perf40-early-round', 'runtime-perf41-matrix-round'),
    ('pes13-nx-0.2.0-perf40-early-round', 'pes13-nx-0.2.0-perf41-matrix-round'),
    ('PES13-NX PERF40 EARLYROUND', 'PES13-NX PERF41 MATRIXROUND'),
    ('perf40_patches as perf23_patches', 'perf41_patches as perf23_patches'),
):
    source = source.replace(old, new)
exec(compile(source, str(path), 'exec'), {'__file__': str(path), '__name__': '__main__'})

report = json.loads((work / 'verification.json').read_text())
report.update(base='PERF40',
              actual_new_change='fingerprinted FASTROUND for 0x112f8f0 only',
              performance_improvement_claimed=False)
(work / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
