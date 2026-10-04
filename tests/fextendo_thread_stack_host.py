"""Check native stack ownership and concurrent pressure under ASan/UBSan."""
import argparse,hashlib,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    checks=[]
    with tempfile.TemporaryDirectory(prefix='fextendo-stack-') as directory:
        binary=Path(directory)/'stack'
        subprocess.run(['gcc','-std=c11','-O1','-g','-pthread','-Wall','-Wextra',
            '-fsanitize=address,undefined',str(ROOT/'tests/fextendo_thread_stack.c'),'-o',str(binary)],check=True)
        for capacity in (0,2,8):
            r=subprocess.run([str(binary),str(capacity)],capture_output=True,text=True)
            print(r.stdout,r.stderr,end='',flush=True);r.check_returncode()
            checks.append({'capacity':capacity,'passed':True,'stdout':r.stdout})
    files=['src/runtime/fextendo_thread_stack.h','tests/fextendo_thread_stack.c','tests/fextendo_thread_stack_host.py']
    report={'passed':True,'hardware_tested':False,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],
        'checks':checks,'sources':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in files}}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
