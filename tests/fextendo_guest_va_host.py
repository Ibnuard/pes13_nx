"""Exercise the production VA policy under ASan/UBSan."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.parent.mkdir(parents=True,exist_ok=True);binary=a.output.with_suffix('.test')
    sources=('src/runtime/fextendo_guest_va.h','tests/fextendo_guest_va_policy.c','tests/fextendo_guest_va_host.py')
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-O1','-g','-fsanitize=address,undefined',
        '-fno-omit-frame-pointer','-I',str(ROOT/'src/runtime'),str(ROOT/sources[1]),'-o',str(binary)],check=True)
    r=subprocess.run([str(binary.resolve())],capture_output=True,text=True,check=True)
    a.output.write_text(json.dumps({'passed':True,'hardware_tested':False,'sanitizers':['address','undefined'],
        'result':r.stdout.strip(),'sources':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sources}},indent=2)+'\n')
    print(r.stdout)
if __name__=='__main__':main()
