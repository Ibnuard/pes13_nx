"""Run repair failures, actual UI/preset gate, console ownership and live pinned download."""
import argparse,hashlib,json,subprocess,tempfile,zipfile,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--network',action='store_true');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    r=subprocess.run(['python3',str(ROOT/'tests/fextendo_runtime_fixer_host.py')],capture_output=True,text=True,check=True)
    (a.output/'fixer-host.json').write_text(r.stdout);print('PASS: fault and interrupted repair recovery',flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp);root=tmp/'root';preview=a.output/'preview';preview.mkdir(exist_ok=True)
        with zipfile.ZipFile(a.archive) as z:
            for n in z.namelist():
                if n.startswith('switch/pes13-fex/launcher/') and not n.endswith('/'):
                    target=root/n[len('switch/pes13-fex/'):];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(n))
        game=root/'drive_c/PES13';(game/'img').mkdir(parents=True)
        exe=bytearray(128);exe[:2]=b'MZ';struct.pack_into('<I',exe,60,64);exe[64:68]=b'PE\0\0';struct.pack_into('<H',exe,68,0x14c);struct.pack_into('<H',exe,88,0x10b)
        (game/'pes2013.exe').write_bytes(exe);(game/'img/dt00.img').write_bytes(b'asset')
        for n in ('fextendo_startup_switch','fextendo_ui','fextendo_runtime_download'):
            if n.endswith('download') and not a.network:continue
            binary=tmp/n;libs=['-lm']
            if n.endswith('download'):libs=['-lcurl','-lminizip','-lz','-lcrypto']
            subprocess.run(['gcc','-std=gnu11','-g','-O1','-Wno-deprecated-declarations','-fsanitize=undefined',str(ROOT/'tests'/(n+'.c')),'-o',str(binary),*libs],check=True)
            commands=[[str(binary),str(root),str(k)] for k in range(5)] if n.endswith('switch') else [[str(binary),str(root),str(preview)]]
            if n.endswith('ui'):
                # The UI regression needs an existing canonical settings file.
                target=root/'drive_c/KONAMI/Pro Evolution Soccer 2013/settings.dat';target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes((root/'launcher/presets/medium-720.dat').read_bytes())
            if n.endswith('download'):
                target=tmp/'download';target.mkdir();commands=[[str(binary),str(target)]]
            outputs=[]
            for cmd in commands:
                r=subprocess.run(cmd,capture_output=True,text=True,timeout=1000)
                assert r.returncode==0 and 'runtime error:' not in r.stderr,(n,r.stdout,r.stderr)
                outputs.append(r.stdout)
            (a.output/(n+'.txt')).write_text('\n'.join(outputs));print('PASS: '+n,flush=True)
    sources=['tests/fextendo_checker_validation.py','tests/fextendo_startup_switch.c','tests/fextendo_ui.c','tests/fextendo_runtime_download.c',
        'tests/fextendo_runtime_fixer_host.py','src/runtime/fextendo_startup_switch.h','src/runtime/fextendo_ui.h',
        'src/runtime/fextendo_settings.h','src/runtime/fextendo_runtime_catalog.h','src/runtime/fextendo_runtime_download.h','src/runtime/fextendo_runtime_fixer.h']
    (a.output/'validation.json').write_text(json.dumps({'passed':True,'hardware_tested':False,'https_tested':a.network,
        'sources':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sources}},indent=2)+'\n')
if __name__=='__main__':main()
