"""Use the established build transaction; never leave the WSL source patched."""
from pathlib import Path
p=Path(__file__).resolve().parents[1]
path=p/'tools/run-perf35-build.py'
text=path.read_text().replace('local/perf35','local/perf37').replace('build-perf35.py','build-perf37.py')
text=text.replace('runtime-perf35-fast-jumptable','runtime-perf37-jit-probe')
exec(compile(text,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})
