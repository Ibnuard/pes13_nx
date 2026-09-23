"""Snapshot/build/restore PERF44 using the established WSL transaction."""
from pathlib import Path

project = Path(__file__).resolve().parents[1]
path = project / 'tools/run-perf42-build.py'
source = path.read_text()
for old, new in (
    ('local/perf42', 'local/perf44'),
    ('build-perf42.py', 'build-perf44.py'),
    ('runtime-perf42-startup-guard', 'runtime-perf44-event-pipeline'),
):
    assert old in source, old
    source = source.replace(old, new)
exec(compile(source, str(path), 'exec'), {'__file__': str(path), '__name__': '__main__'})
