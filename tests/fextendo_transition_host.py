"""Build/run the trace and worker tests on Linux under ASan and UBSan."""
import argparse,hashlib,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    checks=[]
    with tempfile.TemporaryDirectory(prefix='fextendo-trace-') as directory:
        for name,defines,runs in [('fextendo_transition_trace',[],[[]]),
                                  ('fextendo_diagnostics',[],[['0'],['1']]),
                                  ('fextendo_diagnostics',['-DFX_TRANSITION_TRACE'],[['0'],['1']]),
                                  ('fextendo_diagnostics',['-DFX_TRANSITION_TRACE','-DFX_SCRATCH_RESERVE'],[['0'],['1']]),
                                  ('fextendo_diagnostics',['-DFX_TRANSITION_TRACE','-DFX_SCRATCH_RESERVE','-DFX_LIVE_TRACE'],[['0'],['1']]),
                                  ('fextendo_diagnostics',['-DFX_TRANSITION_TRACE','-DFX_SCRATCH_RESERVE','-DFX_LIVE_TRACE','-DFX_SCRATCH_RESERVE_VERSION=3'],[['0'],['1']]),
                                  ('fextendo_diagnostics',['-DFX_TRANSITION_TRACE','-DFX_SCRATCH_RESERVE','-DFX_LIVE_TRACE','-DFX_SCRATCH_RESERVE_VERSION=3','-DFX_PAGE_STORE'],[['0'],['1']]),
                                  ('fextendo_diagnostics',['-DFX_TRANSITION_TRACE','-DFX_SCRATCH_RESERVE','-DFX_LIVE_TRACE','-DFX_SCRATCH_RESERVE_VERSION=3','-DFX_PAGE_STORE','-DFX_THREAD_STACK_RESERVE'],[['0'],['1']]),
                                  ('fextendo_diagnostics',['-DFX_TRANSITION_TRACE','-DFX_SCRATCH_RESERVE','-DFX_LIVE_TRACE','-DFX_SCRATCH_RESERVE_VERSION=3','-DFX_PAGE_STORE','-DFX_THREAD_STACK_RESERVE','-DFX_SCRATCH_PAGES'],[['0'],['1']]),
                                  ('fextendo_live_threads',[],[[]])]:
            binary=Path(directory)/name
            subprocess.run(['gcc','-O1','-g','-std=c11','-pthread','-Wno-deprecated-declarations',
                '-fsanitize=address,undefined',*defines,str(ROOT/'tests'/(name+'.c')),'-o',str(binary)],check=True)
            for args in runs:
                r=subprocess.run([str(binary),*args],capture_output=True,text=True)
                print(r.stdout,r.stderr,end='',flush=True);r.check_returncode()
                checks.append({'test':name,'defines':defines,'args':args,'stdout':r.stdout,'stderr':r.stderr,'passed':True})
    files=['src/runtime/fextendo_transition_trace.h','src/runtime/fextendo_transition_alloc.h',
           'src/runtime/fextendo_diagnostics.h','tests/fextendo_transition_trace.c',
           'tests/fextendo_diagnostics.c','tests/fextendo_transition_host.py',
           'src/runtime/fextendo_live_threads.h','src/runtime/fextendo_live_trace.h','tests/fextendo_live_threads.c']
    r={'passed':True,'hardware_tested':False,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],
       'checks':checks,'sources':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in files}}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n')
if __name__=='__main__':main()
