"""Build the fingerprinted early FASTROUND candidate on PERF39."""
from pathlib import Path
import hashlib
import json

project = Path(__file__).resolve().parents[1]
work = project / 'local/perf40'
work.mkdir(parents=True, exist_ok=True)
capture = project / 'local/perf39/results/447687a6efc4/all-captures/slot-6-x86.bin'
assert len(capture.read_bytes()) == 1113
assert hashlib.sha256(capture.read_bytes()).hexdigest() == (
    'a0a440c231cde7d30387d12ac94725615ba0cd52f6107f448cd16f61637619f6')
source = (project / 'src/runtime/pes13_perf40.h').read_text()
assert '0x9bc4c221c199e08a' in source

path = project / 'tools/build-perf39.py'
text = path.read_text()
for old, new in (
    ('local/perf39', 'local/perf40'),
    ('runtime-perf39-capture-repair', 'runtime-perf40-early-round'),
    ('pes13-nx-0.2.0-perf39-capture-repair', 'pes13-nx-0.2.0-perf40-early-round'),
    ('PES13-NX PERF39 CAPTURE', 'PES13-NX PERF40 EARLYROUND'),
    ('perf39_patches as perf23_patches', 'perf40_patches as perf23_patches'),
):
    text = text.replace(old, new)
exec(compile(text, str(path), 'exec'), {'__file__': str(path), '__name__': '__main__'})

report = json.loads((work / 'verification.json').read_text())
report.update(base='PERF39',
              actual_new_change='fingerprinted pre-present FASTROUND at 0x113027b',
              performance_improvement_claimed=False)
(work / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
