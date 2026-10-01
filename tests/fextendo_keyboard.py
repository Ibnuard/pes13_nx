"""Run host keyboard regressions against the sources used by a preview build."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('build',type=Path);a=p.parse_args();work=a.build.resolve()
    report=json.loads((work/'build-report.json').read_text())
    assert report['native_keyboard_preview']
    sources={name:sha(ROOT/name) for name in report['feature_sources']}
    assert sources==report['feature_sources']
    source=work/'native-source'
    for name,digest in report['generated_sources'].items():assert sha(source/name)==digest,name
    out=work/'host-keyboard-tests';out.mkdir(exist_ok=True)
    logs={}
    jobs=[('keyboard',ROOT/'tests/fextendo_keyboard.c'),
          ('legacy-keyboard',source/'wine-nx-probe/tests/horizon_keyboard.c')]
    if report.get('live_keyboard_overlay'):
        jobs.append(('live-overlay',ROOT/'tests/fextendo_osk.c'))
    for name,test in jobs:
        binary=out/name
        subprocess.run(['clang','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function',
                        '-fsanitize=address,undefined','-g','-I',str(ROOT/'src/runtime'),
                        '-I',str(source/'dlls/ntdll/unix'),str(test),'-o',str(binary)],check=True)
        result=subprocess.run([str(binary)],check=True,text=True,capture_output=True)
        logs[name]=result.stdout.strip();print(logs[name])
    assert sources=={name:sha(ROOT/name) for name in sources}
    receipt={'passed':True,'hardware_tested':False,'sanitizers':['address','undefined'],
             'native_elf_sha256':report['native_elf_sha256'],'feature_sources':sources,
             'test_sources':{str(p.relative_to(ROOT)):sha(p) for p in
                             (ROOT/'tests/fextendo_keyboard.c',Path(__file__).resolve(),
                              *([ROOT/'tests/fextendo_osk.c'] if report.get('live_keyboard_overlay') else []))},'results':logs}
    (work/'host-keyboard-test.json').write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':main()
