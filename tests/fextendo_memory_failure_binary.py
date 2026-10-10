"""Execute actual memory-failure observer: quiet mode, separate budgets, errno."""
import argparse, hashlib, json, struct
from pathlib import Path
from fextendo_commit_binary import Model as Base, reg, MIB

class Model(Base):
    def __init__(self,path):
        super().__init__(path)
        self.debug=False;self.heap_reads=0;self.queries=0;self.reports=[]
        self.q(self.symbols['fake_heap_start'],0x80000000)
        self.q(self.symbols['fake_heap_end'],0x88000000)
    def string(self,p):
        out=bytearray()
        while self.vm.mem_read(p+len(out),1)!=b'\0':
            out+=self.vm.mem_read(p+len(out),1)
            assert len(out)<2048
        return out.decode()
    def hook(self,vm,pc,size,user):
        n=self.names.get(pc,'');x=lambda i:vm.reg_read(reg(i))
        if n=='wine_nx_launch_debug_active':self.ret(int(self.debug))
        elif n=='mallinfo':
            self.heap_reads+=1
            vm.mem_write(x(8),struct.pack('<10I',64*MIB,0,0,0,0,0,0,56*MIB,8*MIB,2*MIB))
            self.ret()
        elif n=='horizon_trace':
            fmt=self.string(x(0))
            assert fmt.startswith(('[MEM-FAIL] v1 ','[MEM-KERNEL] ')),fmt
            self.reports.append([fmt, self.string(x(1)) if fmt.startswith('[MEM-FAIL]') else None,
                                 [x(i) for i in range(2,8)]])
            # Log formatting must not alter the allocation's original errno.
            vm.mem_write(self.data+0x100,struct.pack('<I',99));self.ret()
        elif n=='svcQueryMemory':
            self.queries+=1;super().hook(vm,pc,size,user)
        elif n in ('write','fsFileWrite','open','fopen','malloc','calloc','memalign'):
            raise AssertionError('Observer called '+n)
        else:super().hook(vm,pc,size,user)

def main():
    p=argparse.ArgumentParser();p.add_argument('elf',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();m=Model(a.elf)
    def call(stage):
        m.vm.mem_write(m.data+0x100,struct.pack('<I',12))
        m.call('horizon_memory_failure',stage,0x20730000,0x89000000,0x390000,0xd401)
        assert struct.unpack('<I',m.vm.mem_read(m.data+0x100,4))[0]==12
    for i in range(6):call(i)
    assert not m.reports and not m.queries and not m.heap_reads
    m.debug=True
    for i in range(100):call(3)
    map_reports=[r for r in m.reports if r[1]=='map']
    assert len(map_reports)==2 and m.queries==4 and m.heap_reads==2
    call(1);call(5)
    assert [r[1] for r in m.reports if r[1]]==['map','map','backing','commit']
    assert m.reports[-1][2][:5]==[0x20730000,0x89000000,0x390000,12,0xd401]
    for stage in range(6):
        for i in range(100):call(stage)
    assert m.heap_reads==12 and m.queries==8
    files=('tests/fextendo_memory_failure_binary.py','tests/fextendo_commit_binary.py',
           'tests/fextendo_page_store_binary.py','tests/fex_reservations.py')
    report=dict(passed=True,hardware_tested=False,native_elf_sha256=hashlib.sha256(a.elf.read_bytes()).hexdigest(),
        checks=['Normal launch makes no diagnostic heap/kernel query or trace',
                '100 startup map failures cannot consume backing/commit report budgets',
                'Repeated failures are rate-limited per stage; native status/address/size preserved',
                'Formatting preserves original errno; observer does not allocate or access storage'],
        sources={n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in files})
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
