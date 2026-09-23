"""Snapshot/build/restore using the established WSL build transaction."""
from pathlib import Path
p=Path(__file__).resolve().parents[1]
path=p/'tools/run-perf35-build.py'
text=path.read_text().replace('local/perf35','local/perf38').replace('build-perf35.py','build-perf38.py')
text=text.replace('runtime-perf35-fast-jumptable','runtime-perf38-region-fusion')
exec(compile(text,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})
