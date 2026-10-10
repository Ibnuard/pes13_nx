"""Run the actual bounded observer under ASan/UBSan with concurrent producers."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.parent.mkdir(parents=True,exist_ok=True)
    binary=a.output.with_suffix('.test')
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-O1','-g',
        '-fsanitize=address,undefined','-fno-omit-frame-pointer','-pthread','-I',str(ROOT/'src/runtime'),
        str(ROOT/'tests/fextendo_wait_probe.c'),'-o',str(binary)],check=True)
    r=subprocess.run([str(binary.resolve())],check=True,capture_output=True,text=True)
    report={'passed':True,'hardware_tested':False,'sanitizers':['address','undefined'],
        'concurrent_calls':240000,'result':r.stdout.strip(),
        'sources':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in
            ('src/runtime/fextendo_wait_probe.h','tests/fextendo_wait_probe.c','tests/fextendo_wait_probe_host.py')}}
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(r.stdout)
if __name__=='__main__':main()
