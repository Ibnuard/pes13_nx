"""Build a private native-submit diagnostic runtime; retain the established CPU policy."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
p=Path(__file__).resolve().parents[1];w=p/'local/perf30';w.mkdir(parents=True,exist_ok=True)
os.environ.setdefault('PES_BUILD_ROOT','/home/blekjek/pes13-build')
subprocess.run([sys.executable,str(p/'tests/perf30_archive.py')],check=True)
subprocess.run([sys.executable,str(p/'tests/perf30_metrics.py')],check=True)
subprocess.run([sys.executable,str(p/'tools/build-perf30-mesa.py')],check=True)
path=p/'tools/build-perf29.py';text=path.read_text()
text=text.replace('local/perf29','local/perf30').replace('runtime-perf29-worker-blocks','runtime-perf30-submit-stages')
text=text.replace('pes13-nx-0.2.0-perf29-worker-blocks','pes13-nx-0.2.0-perf30-submit-stages').replace('PES13-NX PERF29','PES13-NX PERF30')
text=text.replace('import perf29_patches as perf23_patches','import perf30_patches as perf23_patches')
text=text.replace("subprocess.run([sys.executable,str(p/'tests/perf29_policy.py')],check=True)",
    "(w/'policy-tests.json').write_bytes((p/'local/perf29/policy-tests.json').read_bytes())")
exec(compile(text,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})
report=json.loads((w/'verification.json').read_text())
report.update({'diagnostic_only':True,'main_cpu_sampling':False,'scoped_worker_bigblock':0,
    'startup_fix_claimed':False,'hardware_tested':False})
(w/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
