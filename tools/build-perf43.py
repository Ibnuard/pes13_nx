"""Build PERF42 plus sampling only; no new game execution policy."""
from pathlib import Path
import json

project = Path(__file__).resolve().parents[1]
work = project / 'local/perf43'
work.mkdir(parents=True, exist_ok=True)
path = project / 'tools/build-perf42.py'
source = path.read_text()
for old, new in (
    ('local/perf42', 'local/perf43'),
    ('runtime-perf42-startup-guard', 'runtime-perf43-match-probe'),
    ('pes13-nx-0.2.0-perf42-startup-guard', 'pes13-nx-0.2.0-perf43-match-probe'),
    ('PES13-NX PERF42 BOOTGUARD', 'PES13-NX PERF43 MATCH PROBE'),
    ('perf42_patches as perf23_patches', 'perf43_patches as perf23_patches'),
):
    assert old in source, old
    source = source.replace(old, new)
exec(compile(source, str(path), 'exec'), {'__file__': str(path), '__name__': '__main__'})
report = json.loads((work / 'verification.json').read_text())
report.update(base='PERF42', actual_new_change='bounded JIT PC/opcode/block sampling',
              execution_policy_unchanged=True, hardware_tested=False,
              performance_improvement_claimed=False)
(work / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
