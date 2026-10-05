"""Sanitizer checks for production preferences, memory gate and screen capture."""
import argparse,hashlib,json,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--assets',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--preview',type=Path,required=True);a=p.parse_args()
    a.preview.mkdir(parents=True,exist_ok=True);checks=[]
    with tempfile.TemporaryDirectory(prefix='fextendo-production-') as d:
        tmp=Path(d);game=tmp/'root';shutil.copytree(a.assets,game/'launcher')
        shutil.copytree(ROOT/'config/fextendo/presets',game/'launcher/presets',dirs_exist_ok=True)
        canonical=game/'drive_c/KONAMI/Pro Evolution Soccer 2013/settings.dat'
        canonical.parent.mkdir(parents=True);shutil.copy2(game/'launcher/presets/medium-720.dat',canonical)
        for name in ('launch_debug','launch_memory','debug_file','ui','preset_failures','renderers'):
            shutil.copytree(ROOT/'config/fextendo/presets',game/'launcher/presets',dirs_exist_ok=True)
            exe=tmp/name
            subprocess.run(['gcc','-std=c11','-O1','-g','-D_POSIX_C_SOURCE=200809L',
                '-fsanitize=address,undefined','-fno-sanitize-recover=all',
                str(ROOT/f'tests/fextendo_{name}.c'),'-pthread','-lm','-o',str(exe)],check=True)
            args=[str(exe)]
            if name=='ui':args += [str(game),str(a.preview.resolve())]
            elif name in ('debug_file','preset_failures','renderers'):args += [str(game)]
            result=subprocess.run(args,capture_output=True,text=True,timeout=150)
            if result.returncode:print(result.stdout,result.stderr,flush=True)
            result.check_returncode()
            checks.append(result.stdout.strip());print(result.stdout.strip(),flush=True)
    files=['tests/fextendo_'+n+'.c' for n in ('launch_debug','launch_memory','debug_file','ui','preset_failures','renderers')]
    files += ['src/runtime/fextendo_'+n+'.h' for n in ('launch_debug','debug_console','debug_file','launch_memory','presets','settings','ui')]
    report={'passed':True,'hardware_tested':False,'checks':checks,
        'sources':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in files}}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
