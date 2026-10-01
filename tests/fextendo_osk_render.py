"""Render and check the actual preview keyboard UI, preserving source hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('build',type=Path);p.add_argument('--assets',type=Path,required=True);a=p.parse_args()
    work=a.build.resolve();report=json.loads((work/'build-report.json').read_text());assert report['live_keyboard_overlay']
    for name,digest in report['feature_sources'].items():assert sha(ROOT/name)==digest,name
    output=work/'render';output.mkdir(exist_ok=True)
    binary=output/'keyboard-render'
    subprocess.run(['clang','-O1','-std=c11','-D_POSIX_C_SOURCE=200809L',
                    '-fsanitize=address,undefined','-g',str(ROOT/'tests/fextendo_osk_render.c'),'-o',str(binary)],check=True)
    subprocess.run([str(binary),str(a.assets.resolve()),str(output)],check=True)
    images=[]
    for path in sorted(output.glob('keyboard-*.ppm')):
        target=path.with_suffix('.png');Image.open(path).save(target);images.append(target)
    for name,digest in report['feature_sources'].items():assert sha(ROOT/name)==digest,name
    receipt={'passed':True,'hardware_tested':False,'native_elf_sha256':report['native_elf_sha256'],
             'font_sha256':sha(a.assets/'launcher/font.bin'),
             'test_sources':{str(f.relative_to(ROOT)):sha(f) for f in
                             (ROOT/'tests/fextendo_osk_render.c',Path(__file__).resolve())},
             'screenshots':{str(path.relative_to(work)):sha(path) for path in images},
             'checks':['Actual C renderer with ASan/UBSan, 1280x360 allocation and row-stride guards',
                       'Every key touch target agrees with drawing bounds',
                       'English normal/Shift/horizontal/queue-full/closing states rendered with controller sprites'],
             'limits':['Host rendering; no Switch VI composition or device frame-time measurement']}
    (work/'render-test.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))

if __name__=='__main__':main()
