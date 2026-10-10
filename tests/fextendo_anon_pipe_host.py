"""ASan/UBSan tests of actual pipe headers with modeled handle bootstrap."""
import argparse,hashlib,json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    source=a.source.read_text();start=source.index('static unsigned int horizon_server_parse_object_attributes(')
    parse=source[start:source.index('\n}\n',start)+3]
    with tempfile.TemporaryDirectory(prefix='kit12-pipe-') as td:
        folder=Path(td);c=folder/'pipe.c';exe=folder/'pipe'
        c.write_text((ROOT/'tests/fextendo_anon_pipe_host.c').read_text().replace('/* PARSE_ATTRIBUTES */',parse))
        subprocess.run(['gcc','-std=gnu11','-O1','-g','-Wall','-Wextra','-pthread',
            '-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer',
            '-I'+str(ROOT/'src/runtime'),'-I'+str(a.source.parent),str(c),'-o',str(exe)],check=True)
        run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=45)
        print(run.stdout,run.stderr,end='',flush=True);run.check_returncode()
    names=['src/runtime/horizon_anon_pipe.h','src/runtime/horizon_anon_pipe_api.h',
        'src/runtime/horizon_anon_pipe_server.h','tools/fextendo_anon_pipe_patches.py',
        'tests/fextendo_anon_pipe_host.c','tests/fextendo_anon_pipe_host.py']
    report={'passed':True,'hardware_tested':False,'sanitizers':['address','undefined'],
        'result':run.stdout.strip(),'sources':{n:sha(ROOT/n) for n in names},
        'horizon_source_sha256':sha(a.source),'limit':'OS/handle bootstrap modeled; actual production pipe/server helpers execute.'}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
