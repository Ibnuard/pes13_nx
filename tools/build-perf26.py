"""WSL build: guarded native returns for newly compiled game code after boot."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,tempfile
from perf26_patches import policy_text
p=Path(__file__).resolve().parents[1]
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
w=p/'local/perf26';w.mkdir(parents=True,exist_ok=True)
(w/'pes13_perf21_callret.h').write_text(policy_text(p))
source=root/'runtime-perf11-source/wine-nx-probe'
subprocess.run([sys.executable,str(p/'tests/perf26_callret.py')],
    env=dict(os.environ,PYTHONPATH=str(p/'local/perf20/linux-libs')),check=True)
with tempfile.TemporaryDirectory(prefix='perf26-policy-',dir=root) as tmp:
    exe=Path(tmp)/'policy'
    subprocess.run(['cc','-O2','-std=gnu11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
        '-I'+str(source/'vendor/box64/src/include'),'-I'+str(source/'vendor/box64/src'),
        str(p/'tests/perf26_policy.c'),'-o',str(exe)],check=True)
    subprocess.run([str(exe),str(p/'local/game/pes2013.exe')],check=True)
# Retained copy emitter and exact semantic test sources have not changed.
copy=json.loads((p/'local/perf25/copy-tests.json').read_text())
for path,digest in copy['source_sha256'].items():assert hashlib.sha256((p/path).read_bytes()).hexdigest()==digest
path=p/'tools/build-perf25.py';text=path.read_text()
text=text.replace('local/perf25','local/perf26').replace('runtime-perf25-paircopy','runtime-perf26-callret')
text=text.replace('pes13-nx-0.2.0-perf25-paircopy','pes13-nx-0.2.0-perf26-callret').replace('PES13-NX PERF25','PES13-NX PERF26')
text=text.replace('import perf25_patches as perf23_patches','import perf26_patches as perf23_patches')
text=text.replace("subprocess.run([sys.executable,str(p/'tests/perf25_copy.py')],env=env,check=True)",
    "(w/'copy-tests.json').write_bytes((p/'local/perf25/copy-tests.json').read_bytes())")
exec(compile(text,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})
report=json.loads((w/'verification.json').read_text())
report.update({'scoped_callret':2,'startup_global_callret':0,'same_math_and_copy_emitters':True,'hardware_tested':False})
(w/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('PERF26 scoped CALLRET=2 built; hardware validation pending',flush=True)
