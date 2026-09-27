"""Run the shipped ARM64 FPU conversion helpers, including all x87 stack TOPs."""
from pathlib import Path
import argparse, hashlib, json, random, struct
from fex_alloc import Model, PARAM

def main():
    if not __debug__: raise RuntimeError('Assertions required')
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('dll',type=Path);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    m=Model(args.dll);source=PARAM+0x3000;external=PARAM+0x4000;restored=PARAM+0x5000
    rng=random.Random(571981)
    checks=0
    edges=[0,1,0xfffffffffffff,0x10000000000000,0x7fefffffffffffff,0x7ff0000000000001,0x7ff8000000000000,0x8000000000000000]
    for reduced in (0,1):
        for top in range(8):
            for repeat in range(16):
                values=edges if repeat==0 else [rng.getrandbits(64) for _ in range(8)]
                raw=b''.join(struct.pack('<QQ',v,0x3fff+i) for i,v in enumerate(values))
                m.vm.mem_write(source,raw)
                m.call('PES13FexExportX87',external,source,top<<11,reduced)
                assert not m.trapped
                m.call('PES13FexImportX87',restored,external,top<<11,0x37f,reduced)
                assert not m.trapped
                actual=bytes(m.vm.mem_read(restored,128))
                expected=b''.join(struct.pack('<QQ',v,0 if reduced else 0x3fff+i) for i,v in enumerate(values))
                assert actual==expected,(reduced,top,repeat)
                if not reduced:
                    assert bytes(m.vm.mem_read(external,16))==raw[top*16:top*16+16]
                checks+=8
    # Explicit 80-bit format for 1.5 at logical ST0, physical register 3.
    raw=bytearray(128);struct.pack_into('<Q',raw,3*16,0x3ff8000000000000);m.vm.mem_write(source,bytes(raw))
    m.call('PES13FexExportX87',external,source,3<<11,1)
    assert bytes(m.vm.mem_read(external,16))==struct.pack('<QQ',0xc000000000000000,0x3fff)
    report={'passed':True,'dll_sha256':hashlib.sha256(args.dll.read_bytes()).hexdigest(),'register_roundtrips':checks,
            'scope':'Actual linked ARM64 PE instructions under Unicorn, not full guest/Horizon execution'}
    args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
