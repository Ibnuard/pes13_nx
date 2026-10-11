"""Keyboard delay persistence and real native/Wine queue regressions."""
import argparse, hashlib, json, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    results=[]
    with tempfile.TemporaryDirectory() as temp:
        temp=Path(temp)
        for name in ('fextendo_keyboard_options','fextendo_keyboard','fextendo_osk','fextendo_keyboard_capture'):
            binary=temp/name
            subprocess.run(['gcc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror',
                '-Wno-unused-function','-Wno-missing-field-initializers','-Wno-misleading-indentation','-fsanitize=undefined',
                '-I',str(ROOT/'src/runtime'),'-I','/home/blekjek/pes13-build/production-input-fix/native-source/dlls/ntdll/unix',
                str(ROOT/'tests'/f'{name}.c'),'-pthread','-o',str(binary)],check=True)
            r=subprocess.run([str(binary),*([str(temp/'prefs')] if name.endswith('options') else [])],capture_output=True,text=True)
            assert not r.returncode and 'runtime error:' not in r.stderr,(r.stdout,r.stderr)
            results.append(r.stdout.strip());print(results[-1],flush=True)
    sources=['tests/fextendo_keyboard_trigger.py','tests/fextendo_keyboard_options.c','tests/fextendo_keyboard.c','tests/fextendo_osk.c',
        'src/runtime/fextendo_presets.h','src/runtime/fextendo_keyboard_options.h','src/runtime/fextendo_keyboard_switch.h',
        'src/runtime/fextendo_keyboard_wine.h','src/runtime/fextendo_osk.h','src/runtime/fextendo_osk_switch.h']
    sources+=['tests/fextendo_keyboard_capture.c','src/runtime/fextendo_keyboard_capture.h']
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps({'passed':True,'hardware_tested':False,'results':results,
        'sources':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in sources}},indent=2)+'\n')
if __name__=='__main__':main()
