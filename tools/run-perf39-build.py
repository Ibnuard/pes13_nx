"""Snapshot/build/restore using the established WSL build transaction."""
from pathlib import Path

project = Path(__file__).resolve().parents[1]
path = project / 'tools/run-perf38-build.py'
source = path.read_text().replace('local/perf38', 'local/perf39')
source = source.replace('build-perf38.py', 'build-perf39.py')
source = source.replace('runtime-perf38-region-fusion', 'runtime-perf39-capture-repair')
exec(compile(source, str(path), 'exec'), {'__file__': str(path), '__name__': '__main__'})
