"""Build startup recovery on PERF40; PERF41 matrix rounding is excluded."""
from pathlib import Path
import json

project = Path(__file__).resolve().parents[1]
work = project / 'local/perf42'
work.mkdir(parents=True, exist_ok=True)
path = project / 'tools/build-perf40.py'
source = path.read_text()
for old, new in (
    ('local/perf40', 'local/perf42'),
    ('runtime-perf40-early-round', 'runtime-perf42-startup-guard'),
    ('pes13-nx-0.2.0-perf40-early-round', 'pes13-nx-0.2.0-perf42-startup-guard'),
    ('PES13-NX PERF40 EARLYROUND', 'PES13-NX PERF42 BOOTGUARD'),
    ('perf40_patches as perf23_patches', 'perf42_patches as perf23_patches'),
):
    assert old in source, old
    source = source.replace(old, new)
exec(compile(source, str(path), 'exec'), {'__file__': str(path), '__name__': '__main__'})
report = json.loads((work / 'verification.json').read_text())
report.update(base='PERF40',
              actual_new_change='bounded startup lookup recovery at 0x0115c36f',
              hardware_tested=False, performance_improvement_claimed=False)
(work / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
