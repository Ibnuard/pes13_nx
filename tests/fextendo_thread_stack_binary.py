"""Run real old/new ARM64 libnx threadCreate and threadClose under fragmentation.

Allocator and Horizon calls are modeled; stack sizing, TLS/reent initialization,
ownership and error paths execute from the delivered ELF. No guest gameplay.
"""
import argparse,hashlib,json,struct
from pathlib import Path
from capstone import Cs,CS_ARCH_ARM64,CS_MODE_ARM
from elftools.elf.elffile import ELFFile
from fex_reservations import Model as NativeModel,arm,reg

class Model(NativeModel):
    def __init__(self,path):
        super().__init__(path)
        self.names={v:k for k,v in self.symbols.items()};self.next=0x80000000;self.alias=0x90000000
        self.allocations={};self.mappings={};self.fail_alloc=False;self.failed_sizes=[];self.freed=[]
        self.fail_map=False;self.fail_create=False;self.fail_unmap=False;self.fail_query=False
        self.create_calls=[];self.closed=[];self.pool='fx_thread_stack_init' in self.symbols
        self.t=self.data+0x1000;self.tls=self.data+0x8000;self.reent=self.data+0x5000
        self.vm.reg_write(arm.UC_ARM64_REG_TPIDRRO_EL0,self.data+0x2000)
        self.vm.reg_write(arm.UC_ARM64_REG_TPIDR_EL0,self.tls)
        self.q(self.data+0x21f0,self.reent)
        for i in (8,16,24):self.q(self.reent+i,0xab000000+i)
    def allocate(self,align,size):
        if self.fail_alloc:
            self.failed_sizes.append(size);self.vm.mem_write(self.data+0x100,struct.pack('<I',12));return 0
        p=self.next;size=(size+align-1)&-align;self.next+=(size+4095)&-4096;self.next+=4096
        self.vm.mem_map(p,(size+4095)&-4096);self.allocations[p]=size;return p
    def hook(self,vm,pc,size,user):
        n=self.names.get(pc,'');x=lambda i:vm.reg_read(reg(i))
        if pc==self.stop:self.returned=True;vm.emu_stop()
        elif n in ('__errno','__errno_location'):self.ret(self.data+0x100)
        elif n=='__aarch64_read_tp':self.ret(self.tls)
        elif n in ('__wrap_aligned_alloc','aligned_alloc'):self.ret(self.allocate(x(0),x(1)))
        elif n=='free':
            p=x(0)
            if p:
                assert p in self.allocations,('unowned free',hex(p))
                assert not any(src==p for src,length in self.mappings.values()),'Freed borrowed stack'
                self.freed.append(p);vm.mem_unmap(p,(self.allocations.pop(p)+4095)&-4096)
            self.ret()
        elif n=='memset':vm.mem_write(x(0),bytes([x(1)&255])*x(2));self.ret(x(0))
        elif n=='memcpy':vm.mem_write(x(0),bytes(vm.mem_read(x(1),x(2))));self.ret(x(0))
        elif n in ('virtmemLock','virtmemUnlock'):self.ret()
        elif n=='virtmemFindStack':
            assert x(1)==0x4000;p=self.alias;self.alias+=((x(0)+4095)&-4096)+0x8000;self.ret(p)
        elif n=='svcMapMemory':
            if self.fail_map:self.ret(0xd401)
            else:
                assert x(1) in self.allocations and x(2)<=self.allocations[x(1)]
                assert not any(src==x(1) for src,length in self.mappings.values())
                vm.mem_map(x(0),x(2));self.mappings[x(0)]=(x(1),x(2));self.ret()
        elif n=='svcUnmapMemory':
            assert self.mappings.get(x(0))==(x(1),x(2))
            if self.fail_unmap:self.ret(0xd401)
            else:del self.mappings[x(0)];vm.mem_unmap(x(0),x(2));self.ret()
        elif n=='svcQueryMemory':
            if self.fail_query:self.ret(0xd401)
            else:
                found=[(p,length) for p,length in self.allocations.items() if p<=x(2)<p+length]
                assert len(found)==1
                p,length=found[0];borrowed=any(src==p for src,n in self.mappings.values())
                vm.mem_write(x(0),struct.pack('<QQIIIIII',p,length,5,int(borrowed),0 if borrowed else 3,0,0,0));self.ret()
        elif n=='svcCreateThread':
            self.create_calls.append([x(i) for i in range(1,6)])
            assert x(4)==59 and x(5)&0xffffffff==0xfffffffe
            if self.fail_create:self.ret(0x1234)
            else:vm.mem_write(x(0),struct.pack('<I',100+len(self.create_calls)));self.ret()
        elif n=='svcCloseHandle':self.closed.append(x(0));self.ret()
        elif n in ('write','fwrite','fsFileWrite','abort'):raise AssertionError('Unexpected '+n)
    def call(self,name,*args):
        self.returned=False;self.vm.reg_write(arm.UC_ARM64_REG_SP,self.stack+0xf000);self.vm.reg_write(reg(30),self.stop)
        for i,arg in enumerate(args):self.vm.reg_write(reg(i),arg&0xffffffffffffffff)
        try:self.vm.emu_start(self.symbols[name],0,count=500000)
        except Exception as e:raise AssertionError((name,hex(self.vm.reg_read(arm.UC_ARM64_REG_PC)))) from e
        assert self.returned,('Unbounded',name);return self.vm.reg_read(reg(0))&0xffffffff
    def init(self):
        if self.pool:self.call('fx_thread_stack_init')
    def create(self,t=None,size=1048576,external=0):
        return self.call('__wrap_threadCreate' if self.pool else 'threadCreate',t or self.t,0x33330000,0x44440000,external,size,59,-2)
    def stats(self):return struct.unpack('<15Q',self.vm.mem_read(self.symbols['fx_stack_stats'],120))
    def validate_tls(self):
        handle,owns,base,mirror,stack_sz,tls_array=struct.unpack('<IIQQQQ',self.vm.mem_read(self.t,40))
        assert owns==1 and not tls_array and base in self.allocations
        assert self.mappings[mirror][0]==base
        args=mirror+stack_sz
        values=struct.unpack('<6Q',self.vm.mem_read(args,48))
        assert values[0:3]==(self.t,0x33330000,0x44440000),values
        reent,tls=values[3:5]
        assert all(self.uq(reent+i)==0xab000000+i for i in (8,16,24))
        start,end=self.symbols['__tdata_lma'],self.symbols['__tdata_lma_end']
        assert bytes(self.vm.mem_read(tls,end-start))==bytes(self.vm.mem_read(start,end-start))
        tls_len=self.symbols['__tls_end']-self.symbols['__tls_start']
        assert bytes(self.vm.mem_read(tls+end-start,tls_len-(end-start)))==bytes(tls_len-(end-start))
        return base

def branch_targets(path,name):
    with path.open('rb') as f:
        e=ELFFile(f);syms={s.name:s for s in e.get_section_by_name('.symtab').iter_symbols()};s=syms[name]
        sec=e.get_section(s['st_shndx']);offset=s['st_value']-sec['sh_addr']
        ins=Cs(CS_ARCH_ARM64,CS_MODE_ARM).disasm(sec.data()[offset:offset+s['st_size']],s['st_value'])
        addresses={int(i.op_str[1:],16) for i in ins if i.mnemonic in ('b','bl') and i.op_str.startswith('#0x')}
        return {n for n,v in syms.items() if v['st_value'] in addresses}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('elf',type=Path);p.add_argument('--before',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    assert '__wrap_threadCreate' in branch_targets(a.elf,'__syscall_thread_create')
    assert '__wrap___libnx_aligned_alloc' in branch_targets(a.elf,'threadCreate')
    assert '__wrap___libnx_free' in branch_targets(a.elf,'threadClose')
    regressions=[]
    for path in (a.before,a.elf):
        m=Model(path);m.init();m.fail_alloc=True;result=m.create()
        assert result==(0x559 if path==a.before else 0),(path,result)
        assert m.failed_sizes==[1052672],m.failed_sizes
        if path==a.elf:
            base=m.validate_tls();assert m.stats()[4]==1
            m.q(m.t+32,0x123);assert m.call('threadClose',m.t)==0x1759 and m.stats()[2]==1
            m.q(m.t+32,0);assert not m.call('threadClose',m.t)
            assert not m.stats()[2] and m.stats()[5]==1 and base not in m.freed
            assert not m.mappings and len(m.closed)==1
            assert not m.create();assert m.validate_tls()==base;assert not m.call('threadClose',m.t)
        regressions.append({'baseline':path==a.before,'status':hex(result),'failed_allocation':m.failed_sizes[0]})
    m=Model(a.elf);m.init();assert not m.create();base=m.validate_tls();assert not m.call('threadClose',m.t);assert base in m.freed and m.stats()[4]==0
    m=Model(a.elf);m.init();m.fail_alloc=True
    for i in range(8):assert not m.create(m.t+i*64)
    assert m.create(m.t+8*64)==0x559 and m.stats()[6]==1 and m.stats()[10]==1
    for i in range(8):assert not m.call('threadClose',m.t+i*64)
    assert not m.stats()[2] and m.stats()[5]==8 and not m.mappings
    m=Model(a.elf);m.init();m.fail_alloc=True;m.fail_map=True
    assert m.create()==0xd401 and m.stats()[2]==0 and m.stats()[5]==1
    m=Model(a.elf);m.init();m.fail_alloc=True;m.fail_create=True
    assert m.create()==0x1234 and m.stats()[2]==0 and m.stats()[5]==1 and not m.mappings
    m=Model(a.elf);m.init();m.fail_alloc=True;m.fail_create=m.fail_unmap=True
    assert m.create()==0x1234 and m.stats()[2]==1 and m.stats()[7]==1 and len(m.mappings)==1 and not m.freed
    m=Model(a.elf);m.init();m.fail_alloc=True;assert not m.create();m.fail_unmap=True
    assert m.call('threadClose',m.t)==0xd401 and m.stats()[2]==1 and m.stats()[5]==0
    m.fail_unmap=False;assert not m.call('threadClose',m.t) and m.stats()[2]==0
    r={'passed':True,'hardware_tested':False,'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
       'baseline_elf_sha256':hashlib.sha256(a.before.read_bytes()).hexdigest(),'regressions':regressions,
       'checks':['Linked pthread native entry and libnx allocation/close calls route through wrappers',
         'Original 1-MiB stack allocation failure returns 0x559; new binary creates thread with identical stack size and TLS/reent layout',
         'Live thread cannot close; exited thread returns reserve after alias unmap; next allocation reuses it',
         'Normal native allocation still frees normally',
         'Eight concurrent stacks succeed; exhaustion returns original OOM without alias reuse',
         'Map/create failures reclaim only after successful rollback; failed rollback quarantines',
         'Close unmap failure retains lease; successful retry returns it']}
    a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
