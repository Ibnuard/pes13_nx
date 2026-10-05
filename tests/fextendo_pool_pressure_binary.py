"""Execute the linked Wine pressure callback, including lock refusal."""
import argparse,hashlib,json,struct
from pathlib import Path
from fextendo_rust_heap_binary import Model as Base,reg,MIB
class Model(Base):
    def __init__(self,path):super().__init__(path);self.busy=False;self.try_calls=0;self.unlock_calls=0
    def hook(self,vm,pc,size,user):
        n=self.names.get(pc)
        if n=='wine_nx_release_idle_backing_pages':return # Execute actual callback.
        if n=='pthread_mutex_trylock':self.try_calls+=1;self.ret(16 if self.busy else 0)
        elif n=='pthread_mutex_unlock':self.unlock_calls+=1;self.ret(0)
        else:super().hook(vm,pc,size,user)
def main():
    p=argparse.ArgumentParser();p.add_argument('elf',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    m=Model(a.elf);m.limit=2*MIB
    base=m.symbols['backing_pages'];stride=528
    def arena(i,used):
        addr=m.raw(2*MIB,4096)
        payload=struct.pack('<QH',addr,512-len(used))+bytes(int(n in used) for n in range(512))+bytes(6)
        assert len(payload)==stride;m.vm.mem_write(base+i*stride,payload);return addr
    idle=arena(0,[]);live=arena(1,[0,511]);m.vm.mem_write(live,b'LIVE')
    m.busy=True;assert m.call('wine_nx_release_idle_backing_pages')==0
    assert idle in m.allocations and live in m.allocations and m.unlock_calls==0
    m.busy=False;assert m.call('wine_nx_release_idle_backing_pages')==2*MIB
    assert idle not in m.allocations and live in m.allocations and m.unlock_calls==1
    assert bytes(m.vm.mem_read(live,4))==b'LIVE'
    # An inconsistent counter must never free an arena with used pages.
    m.vm.mem_write(base+stride+8,struct.pack('<H',512))
    assert m.call('wine_nx_release_idle_backing_pages')==0 and live in m.allocations
    m.vm.mem_write(base+stride+10,bytes(512))
    assert m.call('wine_nx_release_idle_backing_pages')==2*MIB and not m.allocations
    assert m.call('wine_nx_release_idle_backing_pages')==0
    report={'passed':True,'hardware_tested':False,'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
        'checks':['Actual ARM64 callback refuses a busy mapping lock without blocking or freeing',
        'Only completely idle arenas returned; partial/live and inconsistent metadata protected',
        'Repeated trim is idempotent and balanced with trylock/unlock'],
        'sources':{n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in ('tests/fextendo_pool_pressure_binary.py','tests/fextendo_rust_heap_binary.py','tests/fextendo_scratch_pages_binary.py')}}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
