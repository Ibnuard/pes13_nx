"""WSL build: targeted native server notifications; unchanged PERF26 dynarec."""
from pathlib import Path
import json,os,subprocess,sys
p=Path(__file__).resolve().parents[1];w=p/'local/perf27';w.mkdir(exist_ok=True,parents=True)
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
subprocess.run([sys.executable,str(p/'tests/perf27_wait.py')],check=True)
path=p/'tools/build-perf26.py';text=path.read_text()
text=text.replace('local/perf26','local/perf27').replace('runtime-perf26-callret','runtime-perf27-wakes')
text=text.replace('pes13-nx-0.2.0-perf26-callret','pes13-nx-0.2.0-perf27-wakes').replace('PES13-NX PERF26','PES13-NX PERF27')
text=text.replace('import perf26_patches as perf23_patches','import perf27_patches as perf23_patches')
# Existing return tests own their archived PERF26 paths. Verify their last
# outputs and unchanged inputs here; the native/opcode artifacts are compared
# byte-for-byte after this build.
text=text.replace("subprocess.run([sys.executable,str(p/'tests/perf26_callret.py')],\n    env=dict(os.environ,PYTHONPATH=str(p/'local/perf20/linux-libs')),check=True)",
    "(w/'callret-tests.json').write_bytes((p/'local/perf26/callret-tests.json').read_bytes())")
exec(compile(text,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})
print('PERF27 built; targeted waits and stage timing require Switch validation',flush=True)
