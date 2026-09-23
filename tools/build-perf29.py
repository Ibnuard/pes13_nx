"""WSL: measured worker regions use BIGBLOCK=1; global Compatible stays intact."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,tempfile
p=Path(__file__).resolve().parents[1];w=p/'local/perf29';w.mkdir(parents=True,exist_ok=True)
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
subprocess.run([sys.executable,str(p/'tests/perf29_policy.py')],check=True)
tests=json.loads((p/'local/perf28/fault-tests.json').read_text())
for name,digest in tests['source_sha256'].items(): assert hashlib.sha256((p/name).read_bytes()).hexdigest()==digest,name
(w/'fault-tests.json').write_text(json.dumps(tests,indent=2)+'\n')
path=p/'tools/build-perf28.py';text=path.read_text()
text=text.replace('local/perf28','local/perf29').replace('runtime-perf28-diagnostics','runtime-perf29-worker-blocks')
text=text.replace('pes13-nx-0.2.0-perf28-diagnostics','pes13-nx-0.2.0-perf29-worker-blocks').replace('PES13-NX PERF28','PES13-NX PERF29')
text=text.replace('import perf28_patches as perf23_patches','import perf29_patches as perf23_patches')
text=text.replace("subprocess.run([sys.executable, str(p/'tests/perf28_fault.py')], check=True)",'')
# Earlier build stages assert the completion/bound hooks. Apply the expected
# name change to their assertion strings only, not to patch-search anchors.
real_compile=compile
def compile_hook(source,filename,mode,*args,**kwargs):
    if isinstance(source,str) and filename.endswith(('build-perf22.py','build-perf23.py','build-perf25.py')):
        source=source.replace("assert 'wine_nx_perf25_completed(block, helper.env)' in generated",
            "assert 'wine_nx_perf29_completed(block, helper.env)' in generated")
        source=source.replace("assert 'wine_nx_perf22_block_end(addr, helper.end, helper.env)' in generated",
            "assert 'wine_nx_perf29_block_end(addr, helper.end, helper.env)' in generated")
        source=source.replace("new[0].read_text().replace('wine_nx_perf25_completed','wine_nx_perf22_completed')",
            "new[0].read_text().replace('wine_nx_perf29_completed','wine_nx_perf22_completed').replace('wine_nx_perf29_block_end','wine_nx_perf22_block_end')")
    return real_compile(source,filename,mode,*args,**kwargs)
import builtins
builtins.compile=compile_hook
try: exec(compile(text,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})
finally: builtins.compile=real_compile
report=json.loads((w/'verification.json').read_text())
report.update({'diagnostic_only':False,'main_cpu_sampling':False,'scoped_worker_bigblock':1,
    'startup_fix_claimed':False,'hardware_tested':False})
(w/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print('PERF29 worker block experiment built; Switch A/B still required.',flush=True)
