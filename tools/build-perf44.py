"""Build PERF42 gameplay policy with bounded Vulkan stage timing."""
from pathlib import Path
import json

project = Path(__file__).resolve().parents[1]
work = project / 'local/perf44'
work.mkdir(parents=True, exist_ok=True)
path = project / 'tools/build-perf42.py'
source = path.read_text()
for old, new in (
    ('local/perf42', 'local/perf44'),
    ('runtime-perf42-startup-guard', 'runtime-perf44-event-pipeline'),
    ('pes13-nx-0.2.0-perf42-startup-guard', 'pes13-nx-0.2.0-perf44-event-pipeline'),
    ('PES13-NX PERF42 BOOTGUARD', 'PES13-NX PERF44 PIPELINE'),
    ('perf42_patches as perf23_patches', 'perf44_patches as perf23_patches'),
):
    assert old in source, old
    source = source.replace(old, new)
exec(compile(source, str(path), 'exec'), {'__file__': str(path), '__name__': '__main__'})
report = json.loads((work / 'verification.json').read_text())
report.update(base='PERF42', actual_new_change='bounded CPU-side Vulkan stage timing',
              gameplay_policy_unchanged=True, cpu_sampler_enabled=False,
              hardware_tested=False, performance_improvement_claimed=False)
(work / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
