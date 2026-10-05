"""Exercise fatal persistence and failure handling under ASan/UBSan."""
import argparse,hashlib,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    checks=[]
    with tempfile.TemporaryDirectory(prefix='fextendo-crash-') as directory:
      for defines in ([],['-DFX_PAGE_STORE'],['-DFX_PAGE_STORE','-DFX_THREAD_STACK_RESERVE'],['-DFX_PAGE_STORE','-DFX_THREAD_STACK_RESERVE','-DFX_SCRATCH_PAGES'],['-DFX_PAGE_STORE','-DFX_THREAD_STACK_RESERVE','-DFX_SCRATCH_PAGES=2'],['-DFX_SCRATCH_PAGES=2','-DFX_RUST_HEAP','-DFX_NATIVE_ABORT_DETAIL'],['-DFX_SCRATCH_PAGES=2','-DFX_RUST_HEAP','-DFX_SCREEN_DEBUG']):
        binary=Path(directory)/'crash'
        subprocess.run(['gcc','-O1','-g','-std=c11','-D_GNU_SOURCE','-DFX_SCRATCH_RESERVE_VERSION=3','-pthread',*defines,
                        '-fsanitize=address,undefined',str(ROOT/'tests/fextendo_crash.c'),'-o',str(binary)],check=True)
        result=subprocess.run([str(binary)],capture_output=True,text=True)
        print(result.stdout,result.stderr,end='',flush=True);result.check_returncode()
        checks.append({'defines':defines,'stdout':result.stdout,'passed':True})
    names=['src/runtime/fextendo_crash.h','tests/fextendo_crash.c','tests/fextendo_crash_host.py']
    r={'passed':True,'hardware_tested':False,'checks':checks,
       'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],
       'sources':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names}}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n')
if __name__=='__main__':main()
