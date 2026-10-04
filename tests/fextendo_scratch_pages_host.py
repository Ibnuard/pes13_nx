"""Exercise fragmented native workspaces with real Linux shared mappings."""
import argparse,hashlib,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='fextendo-scratch-pages-') as directory:
        binary=Path(directory)/'test'
        subprocess.run(['gcc','-O1','-g','-std=c11','-pthread','-Wall','-Wextra','-fsanitize=address,undefined',str(ROOT/'tests/fextendo_scratch_pages.c'),'-o',str(binary)],check=True)
        r=subprocess.run([str(binary)],capture_output=True,text=True);print(r.stdout,r.stderr,end='',flush=True);r.check_returncode()
    files=['src/fex/horizon_scratch_pages.h','tests/fextendo_scratch_pages.c','tests/fextendo_scratch_pages_host.py']
    report={'passed':True,'hardware_tested':False,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],'stdout':r.stdout,
       'sources':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in files}}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
