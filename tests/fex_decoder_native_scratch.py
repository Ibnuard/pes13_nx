"""Verify new decoder sizes through the unchanged Kit15 ARM64 host callback."""
import argparse,hashlib,json
from pathlib import Path
from fextendo_scratch_binary import Model,BLOCK

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    m=Model(a.elf,8);m.host();m.bootstrap=False
    rows=[]
    for amount in (128,16384,16512,64000,640000):
        used=m.stats()[1]; ptr=m.allocate(amount);rounded=(amount+4095)&-4096
        assert ptr and m.calls[-1]==(4096,rounded)
        assert m.stats()[1]==used,'small request consumed an 8-MiB unit'
        m.vm.mem_write(ptr+amount-4,b'TAIL')
        assert bytes(m.vm.mem_read(ptr+amount-4,4))==b'TAIL'
        m.release(ptr)
        assert m.frees[-1]==ptr
        rows.append(dict(request=amount,physical_allocation=rounded,reserve_consumed=0))
    m.empty()
    # IR requests retain their full two 8-MiB halves and reserve ownership.
    before=len(m.calls);ptr=m.allocate(2*BLOCK)
    assert ptr and m.stats()[1]==2*BLOCK and len(m.calls)==before
    m.vm.mem_write(ptr+2*BLOCK-4,b'IR!!');m.release(ptr);m.empty()
    files=('tests/fex_decoder_native_scratch.py','tests/fextendo_scratch_binary.py','tests/fextendo_silent.py')
    r=dict(passed=True,hardware_tested=False,native_elf_sha256=hashlib.sha256(a.elf.read_bytes()).hexdigest(),
        results=rows,ir_16mib_preserved=True,
        sources={n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in files},
        scope='Actual linked Kit15 ARM64 host ABI, alignment, reserve and release; libc/kernel calls modeled.')
    a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))

if __name__=='__main__':main()
