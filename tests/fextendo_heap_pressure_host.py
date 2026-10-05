"""Run pressure borrowing against the actual generated native adapter."""
import argparse,hashlib,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--adapter',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    with tempfile.TemporaryDirectory(prefix='fextendo-heap-pressure-') as d:
        exe=Path(d)/'test'
        subprocess.run(['gcc','-std=c11','-D_GNU_SOURCE','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all',
            '-pthread','-I',str(a.adapter),str(a.adapter/'horizon_jit.c'),str(ROOT/'tests/fextendo_heap_pressure.c'),
            '-Wl,--wrap=malloc','-Wl,--wrap=aligned_alloc','-Wl,--wrap=free','-o',str(exe)],check=True)
        r=subprocess.run([str(exe)],capture_output=True,text=True);print(r.stdout,r.stderr,end='',flush=True);r.check_returncode()
    files=['src/fex/horizon_scratch_reserve.h','src/fex/horizon_heap_pressure.h','tests/fextendo_heap_pressure.c','tests/fextendo_heap_pressure_host.py']
    report={'passed':True,'hardware_tested':False,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],'stdout':r.stdout,
        'sources':{n:sha(ROOT/n) for n in files},'adapter_sources':{p.relative_to(a.adapter).as_posix():sha(p) for p in sorted(a.adapter.rglob('*')) if p.is_file()}}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
