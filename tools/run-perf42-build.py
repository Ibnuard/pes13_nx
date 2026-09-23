"""Build PERF42 with the inherited snapshot and source-restore transaction."""
from pathlib import Path

project = Path(__file__).resolve().parents[1]
path = project / 'tools/run-perf40-build.py'
source = path.read_text()
for old, new in (
    ('local/perf40', 'local/perf42'),
    ('build-perf40.py', 'build-perf42.py'),
    ('runtime-perf40-early-round', 'runtime-perf42-startup-guard'),
):
    assert old in source, old
    source = source.replace(old, new)
exec(compile(source, str(path), 'exec'), {'__file__': str(path), '__name__': '__main__'})
