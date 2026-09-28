"""Generate the four launcher presets from the user-tested Medium profile."""
from pathlib import Path
import argparse, binascii, hashlib, json, struct, zipfile

ROOT=Path(__file__).resolve().parents[1]
PRESETS=(('medium-720',1280,720,1),('low-720',1280,720,0),('extra-low-540',960,540,0),('high-720',1280,720,2))

def build(out):
    out.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(ROOT/'dist/pes13-fex3-gap-audit.zip') as z:
        original=z.read('switch/pes13-fex/drive_c/PES13/settings.dat')
        dxvk=z.read('switch/pes13-fex/drive_c/PES13/dxvk.conf').decode()
    assert hashlib.sha256(original).hexdigest()=='5821128f0d225c4b5d9e277609c08fc95fa98c17352721f2d79754d4e48f0b68'
    rows={}
    for name,w,h,q in PRESETS:
        d=bytearray(original)
        struct.pack_into('<H',d,14,struct.unpack_from('<H',d,14)[0]|1)
        struct.pack_into('<II',d,16,w,h);struct.pack_into('<I',d,28,q)
        d[12:14]=b'\0\0';struct.pack_into('<H',d,12,(~binascii.crc_hqx(d,0))&65535)
        (out/(name+'.dat')).write_bytes(d)
        rows[name]={'width':w,'height':h,'vsync':True,'quality_word':q,'quality_mapping_verified':False,
                    'sha256':hashlib.sha256(d).hexdigest()}
    assert dxvk.count('d3d9.presentInterval = 0')==1
    dxvk=dxvk.replace('d3d9.presentInterval = 0','d3d9.presentInterval = 1')
    dxvk='\n'.join(line for line in dxvk.splitlines() if not line.startswith('#'))+'\n'
    (out/'dxvk.conf').write_text('# Fextendo: VSync ON; preserve the two-frame queue.\n'+dxvk)
    (out/'presets.json').write_text(json.dumps(rows,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);build(p.parse_args().output)
