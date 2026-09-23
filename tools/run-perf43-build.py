"""Snapshot/build/restore PERF43 using the existing WSL transaction."""
from pathlib import Path

project = Path(__file__).resolve().parents[1]
path = project / 'tools/run-perf42-build.py'
source = path.read_text()
for old, new in (
    ('local/perf42', 'local/perf43'),
    ('build-perf42.py', 'build-perf43.py'),
    ('runtime-perf42-startup-guard', 'runtime-perf43-match-probe'),
):
    assert old in source, old
    source = source.replace(old, new)
exec(compile(source, str(path), 'exec'), {'__file__': str(path), '__name__': '__main__'})
