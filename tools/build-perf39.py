"""Build PERF38 unchanged except for the opt-in fallback capture path."""
from pathlib import Path
import hashlib
import json

project = Path(__file__).resolve().parents[1]
work = project / 'local/perf39'
work.mkdir(parents=True, exist_ok=True)
tests = json.loads((project / 'local/perf38/fusion-tests.json').read_text())
assert tests['branch_cases'] >= 512 and tests['whole_block_bit_identical']
for name, digest in tests['source_sha256'].items():
    assert hashlib.sha256((project / name).read_bytes()).hexdigest() == digest, name
(work / 'fusion-tests.json').write_text(json.dumps(tests, indent=2) + '\n')

path = project / 'tools/build-perf38.py'
source = path.read_text()
for old, new in (
    ('local/perf38', 'local/perf39'),
    ('runtime-perf38-region-fusion', 'runtime-perf39-capture-repair'),
    ('pes13-nx-0.2.0-perf38-region-fusion', 'pes13-nx-0.2.0-perf39-capture-repair'),
    ('PES13-NX PERF38 FUSION', 'PES13-NX PERF39 CAPTURE'),
    ('perf38_patches as perf23_patches', 'perf39_patches as perf23_patches'),
):
    source = source.replace(old, new)
exec(compile(source, str(path), 'exec'), {'__file__': str(path), '__name__': '__main__'})

report = json.loads((work / 'verification.json').read_text())
report.update(base='PERF38', actual_new_change='opt-in fallback-environment block capture',
              performance_improvement_claimed=False)
(work / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
