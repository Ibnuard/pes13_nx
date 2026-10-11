"""Real filesystem validation plus startup failure/repair routing; no real game required."""
import argparse,hashlib,json,struct,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    cases=[]
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp);binary=tmp/'check';root=tmp/'pes13-fex';game=root/'drive_c/PES13'
        (game/'img').mkdir(parents=True)
        exe=bytearray(128);exe[:2]=b'MZ';struct.pack_into('<I',exe,60,64);exe[64:68]=b'PE\0\0'
        struct.pack_into('<H',exe,68,0x14c);struct.pack_into('<H',exe,88,0x10b)
        (game/'pes2013.exe').write_bytes(exe);(game/'img/dt00.img').write_bytes(b'asset')
        subprocess.run(['gcc','-std=gnu11','-O1','-g','-include','stdlib.h','-fsanitize=undefined',
                        str(ROOT/'tests/fextendo_startup_check.c'),'-o',str(binary)],check=True)
        def run(kind,label,target=root):
            before={n:n.read_bytes() for n in root.rglob('*') if n.is_file()}
            r=subprocess.run([str(binary),str(target),str(kind)],capture_output=True,text=True,timeout=30)
            assert r.returncode==0 and 'runtime error:' not in r.stderr,(label,r.stdout,r.stderr)
            assert all(n.read_bytes()==v for n,v in before.items()),'Checker modified a game file'
            cases.append(label)
        for kind,label in [(0,'healthy offline launch is read-only'),(1,'missing runtime auto-repaired then rechecked'),
                           (2,'network failure blocks launch and recovers transaction'),(3,'unreadable runtime blocks launch'),
                           (5,'failed post-repair verification blocks launch'),(6,'damaged journal blocks launch')]:run(kind,label)
        run(4,'wrong root',tmp/'missing')
        data=(game/'pes2013.exe').read_bytes();(game/'pes2013.exe').write_bytes(b'MZ');run(4,'truncated exe')
        (game/'pes2013.exe').write_bytes(data);(game/'img/dt00.img').unlink();run(4,'missing img assets')
        (game/'img/dt00.img').write_bytes(b'asset')
        (root/'launcher').write_text('wrong');run(4,'runtime directory is a file');(root/'launcher').unlink()
        (root/'launcher').symlink_to(tmp,target_is_directory=True);run(4,'symlink directory');(root/'launcher').unlink()
        data=bytearray(data);struct.pack_into('<H',data,68,0x8664);(game/'pes2013.exe').write_bytes(data)
        run(4,'64-bit executable rejected')
    names=['src/runtime/fextendo_startup_check.h','src/runtime/fextendo_install_check.h',
           'tests/fextendo_startup_checks.py','tests/fextendo_startup_check.c']
    report={'passed':True,'hardware_tested':False,'cases':cases,'high_requires_active_patch':True,
        'sources':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names}}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS: '+str(len(cases))+' installation/repair/admission scenarios and High policy')
if __name__=='__main__':main()
