"""Execute the linked startup VA partition; reserve_area/kernel calls modeled.

The logged request and region bounds are real. The occupancy fixture is an
explicit fragmentation model, not a reconstruction of every device mapping.
"""
import argparse,hashlib,json,struct
from pathlib import Path
from fextendo_silent import Model as Base,reg

class Model(Base):
    def __init__(self,path):
        super().__init__(path)
        self.stack_start=0x200000;self.stack_end=0x40000000;self.stack_known=True
        self.ranges=[]
        self.forbidden.update(self.symbols[n] for n in ('malloc','svcMapMemory','svcMapProcessCodeMemory') if n in self.symbols)
    def hook(self,vm,pc,size,user):
        if pc==self.symbols.get('horizon_get_stack_region'):
            vm.mem_write(vm.reg_read(reg(0)),struct.pack('<Q',self.stack_start))
            vm.mem_write(vm.reg_read(reg(1)),struct.pack('<Q',self.stack_end));self.ret(int(self.stack_known))
        elif pc==self.symbols.get('reserve_area'):
            self.ranges.append((vm.reg_read(reg(0)),vm.reg_read(reg(1))));self.ret()
        elif pc in {self.symbols.get('wine_nx_runtime_trace'),self.symbols.get('horizon_trace')}:
            self.ret()
        else:super().hook(vm,pc,size,user)
    def partition(self,enabled,host_limit=0x100000000):
        self.call('horizon_guest_va_set_headroom',enabled);self.ranges=[]
        # Exclude the executable and native/system views just as free_ranges
        # does; neither policy may cross these Wine-owned exclusions.
        free=[(0x200000,0x400000),(0x1c9a000,0x18000000),
              (0x18100000,0x40000000),(0xc2200000,0x100000000)]
        p=self.data+0x7000
        self.vm.mem_write(p,b''.join(struct.pack('<QQ',*r) for r in free))
        self.vm.mem_write(self.symbols['free_ranges'],struct.pack('<Q',p))
        self.vm.mem_write(self.symbols['free_ranges_end'],struct.pack('<Q',p+16*len(free)))
        self.vm.mem_write(self.symbols['host_addr_space_limit'],struct.pack('<Q',host_limit))
        self.vm.mem_write(self.symbols['address_space_start'],struct.pack('<Q',0x200000))
        head=self.symbols['reserved_areas'];self.vm.mem_write(head,struct.pack('<QQ',head,head))
        self.call('horizon_reserve_guest_address_space')
        return list(self.ranges)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('elf',type=Path)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();m=Model(a.elf)
    for value in (0,1):assert m.config('guest_va_headroom',value,1-value)==value
    old=m.partition(0);new=m.partition(1)
    assert old==[(0x200000,0x400000),(0x1c9a000,0x18000000),(0x18100000,0x20100000)],old
    assert new==[(0x200000,0x400000),(0x1c9a000,0x18000000),(0x18100000,0x30000000)],new
    assert m.stack_end-new[-1][1]==256*1024*1024
    # Simulate a nearly filled old guest arena plus native allocations spaced
    # every 12 MiB above it. The extra protected interval can admit the real
    # 0xeb0000 request. We do not pretend that exact device holes were logged.
    size=0xeb0000;old_ceiling=old[-1][1];new_ceiling=new[-1][1]
    fragmented=[(p,p+0xc00000-0x1000) for p in range(old_ceiling,new_ceiling,0xc00000)]
    assert not any(b-p>=size for p,b in fragmented)
    assert new_ceiling-old_ceiling>=size
    assert not m.partition(1,1<<39)
    m.stack_known=False;assert not m.partition(1);m.stack_known=True
    m.stack_end=0x10000000
    assert m.partition(1)==m.partition(0) # Small native regions retain half.
    report={'passed':True,'hardware_tested':False,
        'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
        'guest_ceiling_before':'0x20100000','guest_ceiling_after':'0x30000000',
        'added_protected_va_mib':255,'minimum_native_window_mib':256,
        'checks':['Linked startup clips reservations to Wine free ranges and address limits',
                  'No physical backing allocated by policy; existing native window preserved',
                  'INI control restores previous half-region policy; 39-bit and unknown ranges skip',
                  'Logged 0xeb0000 request fits additional contiguous space in modeled fragmented layout'],
        'sources':{n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in
            ('tests/fextendo_guest_va_binary.py','src/runtime/fextendo_guest_va.h','tools/fextendo_guest_va_patches.py')}}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
