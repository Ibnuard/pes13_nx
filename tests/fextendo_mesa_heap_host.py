"""Sanitize native CPU recovery and idle Wine pool reuse."""
import argparse,hashlib,json,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();checks=[]
    with tempfile.TemporaryDirectory(prefix='fextendo-mesa-heap-') as d:
        # Reintroduce only the old teardown ordering in an isolated fixture.
        # The deterministic same-VA reissue must reproduce its retained owner.
        before=Path(d)/'before'
        for name in ('tests/fextendo_mesa_heap.c','tests/fextendo_scratch_pages.c','src/fex/horizon_scratch_pages.h','src/runtime/fextendo_mesa_heap.h'):
            target=before/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target)
        header=before/'src/fex/horizon_scratch_pages.h';s=header.read_text()
        marker='HOST_LOCK(&fx_sp_lock);s->state=FX_SP_DRAINING;s->cpu_address=NULL;HOST_UNLOCK(&fx_sp_lock);\n    if(s->reservation)'
        assert s.count(marker)==1
        header.write_text(s.replace(marker,'if(s->reservation)'))
        old=Path(d)/'old-order'
        subprocess.run(['gcc','-std=gnu11','-O1','-g','-pthread','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(before/'tests/fextendo_mesa_heap.c'),'-o',str(old)],check=True)
        r=subprocess.run([str(old)],capture_output=True,text=True)
        assert r.returncode and '!used&&!fx_sp_held' in r.stderr and 'concurrency' not in r.stdout,(r.returncode,r.stdout,r.stderr)
        checks.append('Reintroduced old retirement ordering fails deterministic same-address reissue with retained owner; expected failure reproduced')
        print(checks[-1],flush=True)
        for name in ('mesa_heap','pool_pressure'):
            exe=Path(d)/name
            subprocess.run(['gcc','-std=gnu11','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-pthread',
                '-I'+str(a.source/'dlls/ntdll/unix'),str(ROOT/f'tests/fextendo_{name}.c'),'-o',str(exe)],check=True)
            r=subprocess.run([str(exe)],capture_output=True,text=True);print(r.stdout,r.stderr,end='',flush=True);r.check_returncode();checks.append(r.stdout)
    files=('src/runtime/fextendo_mesa_heap.h','src/runtime/horizon_pool_pressure.h','src/fex/horizon_scratch_pages.h',
        'tools/fextendo_page_store_patches.py','tests/fextendo_mesa_heap.c','tests/fextendo_pool_pressure.c','tests/fextendo_mesa_heap_host.py','tests/fextendo_scratch_pages.c')
    report={'passed':True,'hardware_tested':False,'checks':checks,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],
        'sources':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in files},
        'generated_sources':{n:hashlib.sha256((a.source/n).read_bytes()).hexdigest() for n in ('dlls/ntdll/unix/horizon_pool.h','dlls/ntdll/unix/horizon_pool_pressure.h')}}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
