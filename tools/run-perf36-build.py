"""Retain the established snapshot/restore build transaction for PERF36."""
from pathlib import Path
p = Path(__file__).resolve().parents[1]
path = p / 'tools/run-perf35-build.py'
text = path.read_text().replace('local/perf35', 'local/perf36')
text = text.replace('build-perf35.py', 'build-perf36.py')
text = text.replace('runtime-perf35-fast-jumptable', 'runtime-perf36-scoped-fastnan')
exec(compile(text, str(path), 'exec'), {'__file__': str(path), '__name__': '__main__'})
