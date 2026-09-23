"""Snapshot/build/restore PERF41 using the established WSL transaction."""
from pathlib import Path

project = Path(__file__).resolve().parents[1]
path = project / 'tools/run-perf40-build.py'
source = path.read_text().replace('local/perf40', 'local/perf41')
source = source.replace('build-perf40.py', 'build-perf41.py')
source = source.replace('runtime-perf40-early-round', 'runtime-perf41-matrix-round')
exec(compile(source, str(path), 'exec'), {'__file__': str(path), '__name__': '__main__'})
