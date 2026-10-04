"""Check 64-bit aliases and lock-free ordinary frees in the delivered adapter."""
import argparse,hashlib,json
from pathlib import Path
from fextendo_fragmented_heap_binary import Model as Base,MIB

class Model(Base):
    def __init__(self,path):super().__init__(path);self.lock_calls=0
    def hook(self,vm,pc,size,user):
        if self.names.get(pc)=='mutexLock':self.lock_calls+=1
        super().hook(vm,pc,size,user)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('elf',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    m=Model(a.elf);m.host();m.alias=0x2000000000;m.limit=65536
    lookup=m.allocate(MIB);heap=m.heap(MIB+137,65536)
    assert lookup>2**32 and heap>2**32 and heap%65536==0
    m.check_bytes(lookup,MIB);m.check_bytes(heap,MIB+137)
    before=m.lock_calls
    for _ in range(20):
        normal=m.heap(96,64);assert normal<2**32;m.heap_free(normal)
    assert m.lock_calls==before,'Ordinary heap free unnecessarily enters page-owner lock'
    m.release(lookup);m.heap_free(heap);m.clean()
    report={'passed':True,'hardware_tested':False,'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
      'checks':['Scratch/lookup and private-heap aliases above 4 GiB retain 64-bit pointers and alignment',
                'Twenty ordinary allocate/free pairs bypass fallback ownership locks while aliases are live',
                'Both high aliases unmap and return storage completely'],
      'sources':{n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in ('tests/fextendo_fragmented_heap_addresses.py','tests/fextendo_fragmented_heap_binary.py','tests/fextendo_scratch_pages_binary.py')}}
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
