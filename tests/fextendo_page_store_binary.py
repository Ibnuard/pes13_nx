"""Execute both failing Wine call sites in the actual old/new ARM64 ELFs.

Only allocator, kernel, descriptor/handle services and reply I/O are modeled.
The new allocation fallback, Wine metadata and callback traversal run natively
in Unicorn. This is not a Horizon hardware or PES gameplay test.
"""
import argparse, hashlib, json, struct
from pathlib import Path
from fex_reservations import Model as NativeModel, arm, reg

class Model(NativeModel):
    def __init__(self,path,limit=1024*1024):
        super().__init__(path)
        self.limit=limit;self.next=0x80000000;self.allocations={};self.failures=[]
        self.maps={};self.kernel_calls=0;self.fail_map=0;self.fail_unmap=0;self.unmaps=0
        self.reply=b'';self.reservations={};self.desc=self.data+0x2000;self.desc_data=self.data+0x2100
        self.file=None;self.file_pos=0
        self.vm.mem_write(self.desc,struct.pack('<IIQ',3,1,self.desc_data))
        self.names={v:k for k,v in self.symbols.items()}
    def alloc(self,n,aligned=False):
        if aligned and n>self.limit:
            self.failures.append(n);self.vm.mem_write(self.data+0x100,struct.pack('<I',12));return 0
        ptr=self.next;size=(n+4095)&~4095;self.next+=size+4096
        self.vm.mem_map(ptr,size);self.allocations[ptr]=n;return ptr
    def hook(self,vm,pc,size,user):
        s=self.symbols;x=lambda i:vm.reg_read(reg(i));n=self.names.get(pc,'')
        if pc==self.stop:self.returned=True;vm.emu_stop()
        elif n in ('__errno','__errno_location'):self.ret(self.data+0x100)
        elif n in ('__wrap_memalign','memalign'):self.ret(self.alloc(x(1),True))
        elif n in ('__wrap_aligned_alloc','aligned_alloc'):self.ret(self.alloc(x(1),True))
        elif n in ('__wrap_calloc','calloc'):self.ret(self.alloc(x(0)*x(1)))
        elif n in ('__wrap_malloc','malloc'):self.ret(self.alloc(x(0)))
        elif n=='free':
            if x(0):
                p=x(0);assert p in self.allocations,('unowned free',hex(p))
                assert not any(p<=src<p+self.allocations[p] for src,_ in self.maps.values()),'Freed kernel-owned storage'
                length=self.allocations.pop(p);vm.mem_unmap(p,(length+4095)&~4095)
            self.ret()
        elif n=='memset':vm.mem_write(x(0),bytes([x(1)&255])*x(2));self.ret(x(0))
        elif n=='memcpy':vm.mem_write(x(0),bytes(vm.mem_read(x(1),x(2))));self.ret(x(0))
        elif n=='envIsSyscallHinted':self.ret(1)
        elif n=='envGetOwnProcessHandle':self.ret(42)
        elif n in ('pthread_mutex_lock','pthread_mutex_unlock','pthread_mutex_init',
                    'pthread_mutex_destroy','virtmemLock','virtmemUnlock','armDCacheFlush','armICacheInvalidate'):self.ret()
        elif n=='virtmemAddReservation':
            token=self.data+0x3000+len(self.reservations)*32
            self.reservations[token]=(x(0),x(1));self.ret(token)
        elif n=='virtmemRemoveReservation':assert x(0) in self.reservations;self.reservations.pop(x(0));self.ret()
        elif n=='svcMapProcessCodeMemory':
            self.kernel_calls+=1
            if self.kernel_calls==self.fail_map:self.ret(0xd401)
            else:
                assert x(0)==42 and x(1) not in self.maps
                assert any(p<=x(2) and x(2)+x(3)<=p+length for p,length in self.allocations.items())
                assert not any(x(1)<addr+length and addr<x(1)+x(3) for addr,(_,length) in self.maps.items())
                self.maps[x(1)]=(x(2),x(3));self.ret()
        elif n=='svcUnmapProcessCodeMemory':
            self.unmaps+=1
            if self.unmaps==self.fail_unmap:self.ret(0xd401)
            else:
                covering=[(addr,src,length) for addr,(src,length) in self.maps.items()
                          if addr<=x(1) and x(1)+x(3)<=addr+length]
                assert len(covering)==1,(hex(x(1)),x(3),self.maps)
                addr,src,length=covering[0];assert src+x(1)-addr==x(2)
                del self.maps[addr]
                if addr<x(1):self.maps[addr]=(src,x(1)-addr)
                if x(1)+x(3)<addr+length:self.maps[x(1)+x(3)]=(x(2)+x(3),addr+length-x(1)-x(3))
                self.ret()
        elif n=='svcSetProcessMemoryPermission':self.ret()
        elif n in ('horizon_trace','pes13_fex_hmap_failure','wine_nx_runtime_trace',
                    '__wine_dbg_output','__wine_dbg_get_channel_flags'):self.ret()
        elif n in ('FindDevice','AddDevice'):self.ret(3)
        elif n=='__alloc_handle':self.ret(15)
        elif n=='__get_handle':
            if self.file is not None and x(0) in (7,17):self.ret(0)
            else:assert x(0)==15;self.ret(self.desc)
        elif n=='horizon_server_create_handle_locked':
            entry=self.data+0x4000;obj=self.data+0x5000
            vm.mem_write(entry,struct.pack('<IIQ',0x444,0,obj));self.ret(entry)
        elif n=='write':
            if self.file is not None and x(0)==17:
                self.file[self.file_pos:self.file_pos+x(2)]=vm.mem_read(x(1),x(2));self.file_pos+=x(2);self.ret(x(2))
            else:assert x(0)==33;self.reply+=bytes(vm.mem_read(x(1),x(2)));self.ret(x(2))
        elif self.file is not None and n in ('dup','lseek','read','close'):
            assert x(0) in (7,17)
            if n=='dup':self.ret(17)
            elif n=='lseek':assert x(2)==0;self.file_pos=x(1);self.ret(x(1))
            elif n=='read':
                data=bytes(self.file[self.file_pos:self.file_pos+x(2)])
                if data:vm.mem_write(x(1),data)
                self.file_pos+=len(data);self.ret(len(data))
            else:self.ret()
        elif n in ('read','open','fsFileWrite','close','dup','lseek','fstat'):
            raise AssertionError('Unexpected I/O '+n)
    def call(self,name,*args):
        self.returned=False
        self.vm.reg_write(arm.UC_ARM64_REG_SP,self.stack+0xf000)
        self.vm.reg_write(reg(30),self.stop)
        for i,arg in enumerate(args):self.vm.reg_write(reg(i),arg&0xffffffffffffffff)
        self.vm.emu_start(self.symbols[name],0,count=4000000)
        assert self.returned,('did not return',name)
        return self.vm.reg_read(reg(0))
    def backing(self):return self.call('map_backing_at_locked',0x60000000,5*1024*1024,3,-1,0,0,12)
    def section(self):
        self.vm.mem_write(self.data+0x1000,struct.pack('<3I3IQII',0,0,16,0x1f000f,0x08000000,0,16*1024*1024,0,0))
        self.vm.mem_write(self.data+0x1100,struct.pack('<3I',32,33,34))
        self.call('horizon_server_handle_create_mapping',self.data+0x1100,self.data+0x1000,0,0)
        assert len(self.reply)==64  # Fixed-size native wineserver reply packet.
        return struct.unpack_from('<I',self.reply)[0]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf',type=Path);p.add_argument('--before',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();results=[]
    for path in (a.before,a.elf):
        old=path==a.before
        m=Model(path);result=m.backing();assert bool(result)==old,(path,result)
        assert 5*1024*1024 in m.failures
        if old:assert not m.maps and not m.allocations
        else:
            assert len(m.maps)==5 and sum(n for _,n in m.maps.values())==5*1024*1024
            assert list(sorted(m.maps))==[0x60000000+i*1024*1024 for i in range(5)]
        results.append({'baseline':old,'site':'map_backing_at_locked','succeeded':not result,'mapped_pieces':len(m.maps)})
        m=Model(path);status=m.section();assert bool(status)==old,(path,hex(status))
        assert 16*1024*1024 in m.failures
        if old:assert not m.allocations
        else:assert sum(n for n in m.allocations.values() if n==1024*1024)==16*1024*1024
        results.append({'baseline':old,'site':'horizon_server_handle_create_mapping','succeeded':not status,'status':hex(status)})
    m=Model(a.elf);m.fail_map=3;assert m.backing()!=0
    assert not m.maps and not m.reservations and not m.allocations
    m=Model(a.elf);m.fail_map=3;m.fail_unmap=1;assert m.backing()!=0
    assert m.maps and m.reservations and m.allocations
    # Exercise actual protection splitting and unmap/refcount cleanup.
    m=Model(a.elf);assert m.backing()==0
    assert m.call('horizon_mprotect',0x60080000,3*1024*1024,1)==0
    assert m.call('horizon_mprotect',0x60080000,3*1024*1024,3)==0
    assert m.call('horizon_munmap',0x60080000,3*1024*1024)==0
    assert m.call('horizon_munmap',0x60000000,512*1024)==0
    assert m.call('horizon_munmap',0x60380000,1536*1024)==0
    assert not m.maps and not m.allocations and not m.reservations
    m=Model(a.elf);n=5*1024*1024
    original=bytes(range(256))*(n//256);m.file=bytearray(original[:-4096])
    assert m.call('map_backing_at_locked',0x60000000,n,3,7,0,1,12)==0
    for addr,(src,length) in m.maps.items():
        off=addr-0x60000000;expected=original[off:off+length] if off+length<n else original[off:n-4096]+bytes(4096)
        assert bytes(m.vm.mem_read(src,length))==expected
        m.vm.mem_write(src,b'X')
    assert m.call('horizon_munmap',0x60000000,n)==0
    assert len(m.file)==n and all(m.file[i*1024*1024]==88 for i in range(5))
    assert m.file[-4096:]==bytes(4096)
    assert not m.maps and not m.allocations and not m.reservations
    r={'passed':True,'hardware_tested':False,'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
       'baseline_elf_sha256':hashlib.sha256(a.before.read_bytes()).hexdigest(),'regressions':results,
       'checks':['Execute both original Wine call sites with large allocations denied but small pieces available',
                 '5-MiB backing maps five pieces at contiguous guest addresses',
                 '16-MiB anonymous section returns STATUS_SUCCESS',
                 'Mid-map OS failure removes aliases, reservations and allocations',
                 'Failed rollback quarantines the backing and reservation without freeing aliased pages',
                 'Actual Wine mprotect and munmap split across pieces and release backing after last view',
                 'Actual file-backed reads preserve offsets/EOF zeros; shared writeback retains modifications across all pieces']}
    a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
