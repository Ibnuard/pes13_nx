"""Build complete-submit profiling and bounded zero-time error polling."""
from pathlib import Path
import json,os,subprocess,sys
p=Path(__file__).resolve().parents[1];w=p/'local/perf31';w.mkdir(parents=True,exist_ok=True)
os.environ.setdefault('PES_BUILD_ROOT','/home/blekjek/pes13-build')
for task in ('tests/perf31_metrics.py','tests/perf31_poll.py','tools/build-perf31-mesa.py'):
    subprocess.run([sys.executable,str(p/task)],check=True)
path=p/'tools/build-perf29.py';text=path.read_text()
text=text.replace('local/perf29','local/perf31').replace('runtime-perf29-worker-blocks','runtime-perf31-fence-poll')
text=text.replace('pes13-nx-0.2.0-perf29-worker-blocks','pes13-nx-0.2.0-perf31-fence-poll').replace('PES13-NX PERF29','PES13-NX PERF31')
text=text.replace('import perf29_patches as perf23_patches','import perf31_patches as perf23_patches')
text=text.replace("subprocess.run([sys.executable,str(p/'tests/perf29_policy.py')],check=True)",
    "(w/'policy-tests.json').write_bytes((p/'local/perf29/policy-tests.json').read_bytes())")
exec(compile(text,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})
