"""Compare Kit13/Kit14 storage lifetime using real pipe code under ASan/UBSan."""
import argparse,hashlib,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--before',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();checks=[]
    with tempfile.TemporaryDirectory(prefix='kit14-lifetime-') as td:
        for old in (True,False):
            header=a.before if old else ROOT/'src/runtime/horizon_anon_pipe.h'
            exe=Path(td)/('before' if old else 'after')
            subprocess.run(['gcc','-std=gnu11','-O1','-g','-Wall','-Wextra','-pthread',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',*(['-DBASELINE'] if old else []),
                '-I'+str(header.parent),str(ROOT/'tests/fextendo_pipe_lifetime.c'),'-o',str(exe)],check=True)
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=60)
            print(run.stdout,run.stderr,end='',flush=True);run.check_returncode()
            checks.append({'baseline':old,'passed':True,'header_sha256':sha(header),'result':run.stdout.strip()})
    names=('src/runtime/horizon_anon_pipe.h','tests/fextendo_pipe_lifetime.c','tests/fextendo_pipe_lifetime_host.py')
    report={'passed':True,'hardware_tested':False,'checks':checks,'budget_bytes':8388608,
        'sources':{n:sha(ROOT/n) for n in names},'sanitizers':['address','undefined'],
        'limit':'Real pipe/locks with a modeled allocation budget and deliberately retained writers; not a Switch run.'}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
