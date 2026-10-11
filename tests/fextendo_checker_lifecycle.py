"""Launcher cancellation, settings and one-owner handoff after startup checks."""
import argparse,hashlib,json,subprocess,tempfile,zipfile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from fextendo_startup_assets import generate
from fextendo_install_fixture import make_game
def main():
    p=argparse.ArgumentParser();p.add_argument('--archive',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        tmp=Path(tmp);binary=tmp/'lifecycle'
        embedded=tmp/'startup_assets.c';generate(embedded)
        subprocess.run(['gcc','-std=gnu11','-O1','-g','-fsanitize=undefined',
            str(ROOT/'tests/fextendo_lifecycle.c'),str(embedded),'-o',str(binary),'-lm','-lpthread'],check=True)
        cases=[]
        for k in (0,1,2,5,6,8,9,10,11,12,13,14):
            root=tmp/str(k);root.mkdir()
            with zipfile.ZipFile(a.archive) as z:
                for n in z.namelist():
                    if n.startswith('switch/pes13-fex/launcher/') and not n.endswith('/'):
                        target=root/n[len('switch/pes13-fex/'):];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(n))
            game=root/'game.exe';game.write_bytes(b'MZ')
            make_game(root/'drive_c/PES13')
            (root/'launcher/selected.txt').write_text('0\n')
            target=root/'drive_c/KONAMI/Pro Evolution Soccer 2013/settings.dat';target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((root/'launcher/presets/medium-720.dat').read_bytes())
            if k==13:(root/'launcher/font.bin').unlink()
            if k==2:game=root/'missing.exe'
            r=subprocess.run([str(binary),str(root),str(game),str(k)],capture_output=True,text=True,timeout=45)
            assert r.returncode==0 and 'runtime error:' not in r.stderr,(k,r.stdout,r.stderr)
            cases.append({'mode':k,'passed':True})
    sources=['src/runtime/fextendo_launcher.h','src/runtime/fextendo_startup_switch.h','src/runtime/fextendo_startup_cache.h',
        'src/runtime/fextendo_startup_art.h','src/runtime/fextendo_startup_view.h','tests/fextendo_lifecycle.c','tests/fextendo_checker_lifecycle.py']
    a.output.write_text(json.dumps({'passed':True,'cases':cases,'hardware_tested':False,
        'sources':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sources}},indent=2)+'\n')
    print('PASS: 12 real-thread launcher/modal/retry/maintenance/framebuffer handoff cases')
if __name__=='__main__':main()
