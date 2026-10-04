"""Run the generated native adapter with real host memory and ASan/UBSan."""
import argparse,hashlib,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--adapter',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    checks=[]
    max_units=8 if '#define FX_SCRATCH_UNITS 8u\n' in (a.adapter/'horizon_jit.c').read_text() else 4
    with tempfile.TemporaryDirectory(prefix='fextendo-scratch-') as directory:
        for test in ['fextendo_scratch_arena','fex_heap_native']:
            binary=Path(directory)/test
            command=['gcc','-std=c11','-D_GNU_SOURCE','-O1','-g','-fsanitize=address,undefined','-pthread',
                     '-I',str(a.adapter),str(a.adapter/'horizon_jit.c'),str(ROOT/'tests'/(test+'.c')),'-o',str(binary)]
            if test=='fextendo_scratch_arena':command+=['-Wl,--wrap=aligned_alloc','-Wl,--wrap=free','-DFX_SCRATCH_TEST_UNITS='+str(max_units)]
            subprocess.run(command,check=True)
            for args in ([[str(n)] for n in (0,1,2,4,8) if n<=max_units] if test=='fextendo_scratch_arena' else [[]]):
                r=subprocess.run([str(binary),*args],capture_output=True,text=True)
                print(r.stdout,r.stderr,end='',flush=True);r.check_returncode()
                checks.append(dict(test=test,args=args,passed=True,stdout=r.stdout,stderr=r.stderr))
    r={'passed':True,'hardware_tested':False,'checks':checks,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],
       'adapter_sources':{str(p.relative_to(a.adapter)):sha(p) for p in sorted(a.adapter.rglob('*')) if p.is_file()},
       'sources':{n:sha(ROOT/n) for n in ['src/fex/horizon_scratch_reserve.h','tests/fextendo_scratch_arena.c','tests/fextendo_scratch_host.py','tests/fex_heap_native.c']}}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n')
if __name__=='__main__':main()
