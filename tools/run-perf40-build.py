"""Snapshot/build/restore PERF40 using the established WSL transaction."""
from pathlib import Path

project = Path(__file__).resolve().parents[1]
path = project / 'tools/run-perf39-build.py'
source = path.read_text().replace('local/perf39', 'local/perf40')
source = source.replace('build-perf39.py', 'build-perf40.py')
source = source.replace('runtime-perf39-capture-repair', 'runtime-perf40-early-round')
exec(compile(source, str(path), 'exec'), {'__file__': str(path), '__name__': '__main__'})
