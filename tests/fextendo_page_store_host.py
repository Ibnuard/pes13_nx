"""Fault-injected Wine page backing/section tests, using real Linux shared pages."""
import argparse, hashlib, json, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--frozen',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();checks=[]
    with tempfile.TemporaryDirectory(prefix='fextendo-pages-') as tmp:
        for baseline in (True,False):
            binary=Path(tmp)/('baseline' if baseline else 'candidate')
            include=(a.frozen if baseline else a.source)/'dlls/ntdll/unix'
            subprocess.run(['gcc','-O1','-g','-std=gnu11','-Wall','-Wextra','-pthread',
                '-fsanitize=address,undefined',*(['-DTEST_BASELINE'] if baseline else []),
                '-I'+str(include),str(ROOT/'tests/fextendo_page_store.c'),'-o',str(binary)],check=True)
            r=subprocess.run([str(binary)],text=True,capture_output=True)
            print(r.stdout,r.stderr,end='',flush=True);r.check_returncode()
            checks.append({'baseline':baseline,'stdout':r.stdout,'passed':True})
    names=('src/runtime/horizon_page_store.h','src/runtime/horizon_store_backing.h',
           'tools/fextendo_page_store_patches.py','tests/fextendo_page_store.c','tests/fextendo_page_store_host.py')
    report={'passed':True,'hardware_tested':False,'checks':checks,
            'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],
            'sources':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names},
            'generated_sources':{n:hashlib.sha256((a.source/n).read_bytes()).hexdigest()
                for n in ('dlls/ntdll/unix/horizon.c','dlls/ntdll/unix/horizon_memfile.h')}}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
