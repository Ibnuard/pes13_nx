"""Reproduce Kit12's serial pipe write stall, then test the actual replacement."""
import argparse,hashlib,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();results=[]
    with tempfile.TemporaryDirectory(prefix='kit13-quota-') as td:
        for old in (True,False):
            header=args.before if old else ROOT/'src/runtime/horizon_anon_pipe.h'
            exe=Path(td)/('before' if old else 'after')
            subprocess.run(['gcc','-std=gnu11','-O1','-g','-Wall','-Wextra','-pthread',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                *(['-DBASELINE'] if old else []),'-I'+str(header.parent),
                str(ROOT/'tests/fextendo_pipe_quota.c'),'-o',str(exe)],check=True)
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20)
            print(run.stdout,run.stderr,end='',flush=True);run.check_returncode()
            results.append({'baseline':old,'passed':True,'result':run.stdout.strip(),'header_sha256':sha(header)})
    names=('src/runtime/horizon_anon_pipe.h','tests/fextendo_pipe_quota.c','tests/fextendo_pipe_quota_host.py')
    report={'passed':True,'hardware_tested':False,'sanitizers':['address','undefined'],
        'checks':results,'requested_bytes':2101740,'inferred_kserv_payload_bytes':1050870,
        'sources':{n:sha(ROOT/n) for n in names},
        'limit':'Real native pthread pipe behavior, with only allocation failure injected. Not Switch PES execution.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
