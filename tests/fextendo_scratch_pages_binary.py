"""Reproduce the logged 56-MiB live reserve plus failing 16-MiB FEX request.

Executes the linked scratch host callbacks, reserve, page fallback and teardown.
Only allocator, virtual address reservation and Horizon syscalls are modeled.
"""
import argparse,hashlib,json,struct
from pathlib import Path
from fex_reservations import Model as NativeModel,arm,reg
MIB=1024*1024
class Model(NativeModel):
    def __init__(self,path):
        super().__init__(path);self.names={v:k for k,v in self.symbols.items()}
        self.next=0x80000000;self.alias=0xb0000000;self.allocations={};self.maps={};self.reservations={};self.locks=[]
        self.bootstrap=True;self.limit=MIB;self.fail_after=None;self.failed_allocations=[]
        self.map_calls=0;self.fail_map=0;self.unmap_calls=0;self.fail_unmap=0;self.no_va=False;self.no_reservation=False
    def hook(self,vm,pc,size,user):
        n=self.names.get(pc,'');x=lambda i:vm.reg_read(reg(i))
        if pc==self.stop:self.returned=True;vm.emu_stop()
        elif n in ('__errno','__errno_location'):self.ret(self.data+0x100)
        elif n=='mutexLock':assert x(0) not in self.locks;self.locks.append(x(0));self.ret()
        elif n=='mutexUnlock':assert self.locks.pop()==x(0);self.ret()
        elif n=='aligned_alloc':
            assert not self.locks and x(0)==4096 and not x(1)%4096
            if (not self.bootstrap and x(1)>self.limit) or self.fail_after==0:
                self.failed_allocations.append(x(1));vm.mem_write(self.data+0x100,struct.pack('<I',12));self.ret(0)
            else:
                p=self.next;self.next+=x(1)+4096;vm.mem_map(p,x(1));self.allocations[p]=x(1)
                if self.fail_after is not None:self.fail_after-=1
                self.ret(p)
        elif n=='free':
            assert not self.locks
            p=x(0);assert p in self.allocations
            assert not any(src==p for src,length in self.maps.values()),'Freed borrowed compiler source'
            vm.mem_unmap(p,self.allocations.pop(p));self.ret()
        elif n=='virtmemLock':assert not self.locks;self.locks.append('vm');self.ret()
        elif n=='virtmemUnlock':assert self.locks.pop()=='vm';self.ret()
        elif n=='virtmemFindStack':
            assert self.locks==['vm'] and x(1)==4096
            if self.no_va:self.ret(0)
            else:p=self.alias;self.alias+=x(0)+0x8000;self.ret(p)
        elif n=='virtmemAddReservation':
            assert self.locks==['vm']
            if self.no_reservation:self.ret(0)
            else:p=self.data+0x2000+len(self.reservations)*32;self.reservations[p]=(x(0),x(1));self.ret(p)
        elif n=='virtmemRemoveReservation':
            assert self.locks==['vm'];addr,length=self.reservations.pop(x(0))
            assert not any(addr<=alias<addr+length for alias in self.maps);self.ret()
        elif n=='svcMapMemory':
            assert not self.locks;self.map_calls+=1
            if self.map_calls==self.fail_map:self.ret(0xd401)
            else:
                assert x(1) in self.allocations and self.allocations[x(1)]==x(2)
                assert any(addr<=x(0) and x(0)+x(2)<=addr+length for addr,length in self.reservations.values())
                vm.mem_map(x(0),x(2));self.maps[x(0)]=(x(1),x(2));self.ret()
        elif n=='svcUnmapMemory':
            assert not self.locks;self.unmap_calls+=1;assert self.maps.get(x(0))==(x(1),x(2))
            if self.unmap_calls==self.fail_unmap:self.ret(0xd401)
            else:del self.maps[x(0)];vm.mem_unmap(x(0),x(2));self.ret()
        elif n=='snprintf':vm.mem_write(x(0),b'\0');self.ret(0)
        elif n in ('write','fsFileWrite','abort'):raise AssertionError('Unexpected '+n)
    def call(self,name,*args):
        self.returned=False;self.vm.reg_write(arm.UC_ARM64_REG_SP,self.stack+0xf000);self.vm.reg_write(reg(30),self.stop)
        for i,arg in enumerate(args):self.vm.reg_write(reg(i),arg&0xffffffffffffffff)
        try:self.vm.emu_start(self.symbols[name],0,count=2000000)
        except Exception as e:raise AssertionError((name,hex(self.vm.reg_read(arm.UC_ARM64_REG_PC)))) from e
        assert self.returned,('Unbounded',name);return self.vm.reg_read(reg(0))
    def host(self):
        table=self.call('pes13_fex_native_host');assert struct.unpack('<4I',self.vm.mem_read(table,16))==(0x46455848,3,96,0)
        self.symbols['allocate']=self.uq(table+56);self.symbols['release']=self.uq(table+64);self.bootstrap=False
    def allocate(self,n):return self.call('allocate',n)
    def release(self,p):self.call('release',p)
    def stats(self):
        self.call('pes13_fex_scratch_pages_snapshot',self.data);return struct.unpack('<15Q',self.vm.mem_read(self.data,120))
    def fill_reserve(self):
        pointers=[self.allocate(n*MIB) for n in (16,16,8,8,8)]
        assert all(pointers) and len(set(pointers))==5
        for i,p in enumerate(pointers):self.vm.mem_write(p,bytes([i+1])*4)
        return pointers

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('elf',type=Path);p.add_argument('--before',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    regressions=[]
    for path in (a.before,a.elf):
        m=Model(path);m.host();owners=m.fill_reserve();buf=m.allocate(16*MIB)
        assert bool(buf)==(path==a.elf) and 16*MIB in m.failed_allocations
        if buf:
            assert len(m.maps)==16 and sum(n for _,n in m.maps.values())==16*MIB
            for off in range(0,16*MIB,4096):m.vm.mem_write(buf+off,b'PAGE')
            for off in range(0,16*MIB,4096):assert bytes(m.vm.mem_read(buf+off,4))==b'PAGE'
            for i,pointer in enumerate(owners):assert bytes(m.vm.mem_read(pointer,4))==bytes([i+1])*4
            m.release(buf+4096);assert len(m.maps)==16 and m.stats()[11]==1
            m.release(buf);assert not m.maps and not m.reservations and m.stats()[3:7]==(0,16*MIB,0,0)
        for pointer in owners:m.release(pointer)
        assert len(m.allocations)==1  # Only preallocated 64-MiB arena remains.
        regressions.append({'baseline':path==a.before,'live_reserve_bytes':56*MIB,'request_bytes':16*MIB,'succeeded':bool(buf)})
    m=Model(a.elf);m.host();m.fill_reserve();m.limit=64*1024;p=m.allocate(16*MIB)
    assert p and len(m.maps)==256;m.release(p);assert not m.maps and len(m.allocations)==1
    for scenario in ('no_va','no_reservation','map','heap','rollback','release'):
        m=Model(a.elf);m.host();m.fill_reserve()
        if scenario in ('no_va','no_reservation'):setattr(m,scenario,True)
        if scenario in ('map','rollback'):m.fail_map=5
        if scenario=='heap':m.fail_after=3
        if scenario=='rollback':m.fail_unmap=2
        buf=m.allocate(16*MIB)
        if scenario=='release':assert buf;m.fail_unmap=4;m.release(buf)
        else:assert not buf
        if scenario in ('rollback','release'):
            assert m.stats()[10]==1 and m.stats()[3]==16*MIB and m.maps and m.reservations and len(m.allocations)==17
        else:assert m.stats()[3]==0 and not m.maps and not m.reservations and len(m.allocations)==1
    report={'passed':True,'hardware_tested':False,'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
      'baseline_elf_sha256':hashlib.sha256(a.before.read_bytes()).hexdigest(),'regressions':regressions,
      'checks':['Execute original ABI scratch callbacks with 56-MiB reserve occupied and 16-MiB contiguous heap failure',
       'New callback supplies contiguous 16-MiB alias from sixteen 1-MiB allocations; original returns NULL',
       'All pages writable; live reserve contents retained; teardown unmaps before freeing',
       'Fragmentation down to 64-KiB chunks succeeds with 256 mappings',
       'Heap/VA/reservation/map failure returns NULL and releases all recoverable resources',
       'Failed rollback/release quarantines source storage and reservation without unsafe reuse'],
      'sources':{'tests/fextendo_scratch_pages_binary.py':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
