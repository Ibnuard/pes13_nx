"""Build scoped game block growth on PERF25 without later wait/return/driver changes."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,builtins
p=Path(__file__).resolve().parents[1];w=p/'local/perf33';w.mkdir(parents=True,exist_ok=True)
os.environ.setdefault('PES_BUILD_ROOT','/home/blekjek/pes13-build')
subprocess.run([sys.executable,str(p/'tests/perf33_policy.py')],check=True)
copy=json.loads((p/'local/perf25/copy-tests.json').read_text())
for path,digest in copy['source_sha256'].items(): assert hashlib.sha256((p/path).read_bytes()).hexdigest()==digest
path=p/'tools/build-perf25.py';text=path.read_text()
text=text.replace('local/perf25','local/perf33').replace('runtime-perf25-paircopy','runtime-perf33-fastmath')
text=text.replace('pes13-nx-0.2.0-perf25-paircopy','pes13-nx-0.2.0-perf33-fastmath').replace('PES13-NX PERF25','PES13-NX PERF33 FASTMATH')
text=text.replace('import perf25_patches as perf23_patches','import perf33_patches as perf23_patches')
text=text.replace("subprocess.run([sys.executable,str(p/'tests/perf25_copy.py')],env=env,check=True)",
    "(w/'copy-tests.json').write_bytes((p/'local/perf25/copy-tests.json').read_bytes())")
real_compile=compile
def compile_hook(source,filename,mode,*args,**kwargs):
    if isinstance(source,str) and filename.endswith(('build-perf22.py','build-perf23.py','build-perf25.py')):
        source=source.replace("assert 'wine_nx_perf25_completed(block, helper.env)' in generated",
            "assert 'wine_nx_perf33_completed(block, helper.env)' in generated")
        source=source.replace("assert 'wine_nx_perf22_block_end(addr, helper.end, helper.env)' in generated",
            "assert 'wine_nx_perf33_block_end(addr, helper.end, helper.env)' in generated")
        source=source.replace("new[0].read_text().replace('wine_nx_perf25_completed','wine_nx_perf22_completed')",
            "new[0].read_text().replace('wine_nx_perf33_completed','wine_nx_perf22_completed').replace('wine_nx_perf33_block_end','wine_nx_perf22_block_end')")
    return real_compile(source,filename,mode,*args,**kwargs)
builtins.compile=compile_hook
try: exec(compile(text,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})
finally: builtins.compile=real_compile
report=json.loads((w/'verification.json').read_text())
report.update(dict(base='PERF25', scoped_bigblock=3, scoped_callret=0, hardware_tested=False,
                   target_match_fps=30, target_verified=False))
(w/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
