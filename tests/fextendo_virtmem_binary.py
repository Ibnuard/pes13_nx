"""Execute the delivered libnx manager and CPU alias protocol, not a mock finder.

The r5 model uses the recorded 32-bit no-alias regions. Kernel block occupancy
is a reproduction fixture, not a claim that every console mapping was logged.
Actual ARM64 search/reservations/map/free run; kernel, malloc and RNG are modeled.
"""
import argparse,hashlib,json,struct,random
from pathlib import Path
from fextendo_fragmented_heap_binary import Model as Base,MIB,reg

PAGE=4096
class Model(Base):
    def __init__(self,path):
        super().__init__(path)
        self.rng=0x22000;self.random_calls=0;self.query_calls=0;self.query_error=False
        self.blocked=[];self.meta={};self.serial=0;self.permissions={}
        self.low=0x200000;self.high=0x100000000
        self.stack_end=0x40000000;self.heap_low=0x41e00000;self.heap_end=0xc1e00000
        self.regions()
    def regions(self):
        for n,a,b in [('g_StackRegion',self.low,self.stack_end),('g_AslrRegion',self.low,self.high),
                      ('g_HeapRegion',self.heap_low,self.heap_end),('g_AliasRegion',0,0)]:
            self.vm.mem_write(self.symbols[n],struct.pack('<QQ',a,b))
    def reservations_live(self):
        p=self.uq(self.symbols['g_Reservations']);out={}
        while p:
            nxt,prev,a,b=struct.unpack('<4Q',self.vm.mem_read(p,32));assert p in self.meta
            assert p not in out;out[p]=(a,b-a);p=nxt
        return out
    def hook(self,vm,pc,size,user):
        n=self.names.get(pc,'');x=lambda i:vm.reg_read(reg(i))
        if n in ('virtmemLock','virtmemUnlock','virtmemFindStack','virtmemFindCodeMemory',
                 'virtmemFindAslr','virtmemAddReservation','virtmemRemoveReservation'):
            return # Execute the linked manager, including its reservation list.
        if n=='mutexIsLockedByCurrentThread':self.ret(x(0) in self.locks)
        elif n in ('__libnx_virtmem_rng','randomGet64'):
            self.random_calls+=1;self.ret(self.rng)
        elif n=='__libnx_alloc':
            assert self.locks==[self.symbols['g_VirtmemMutex']] and x(0)==32
            if self.no_reservation:self.ret(0)
            else:
                p=self.data+0x4000+self.serial*32;self.serial+=1;assert p<self.data+0xf000
                self.meta[p]=32;self.ret(p)
        elif n in ('__libnx_free','__wrap___libnx_free'):
            assert self.locks==[self.symbols['g_VirtmemMutex']];assert x(0) in self.meta
            del self.meta[x(0)];self.ret()
        elif n=='svcQueryMemory':
            assert self.locks==[self.symbols['g_VirtmemMutex']];self.query_calls+=1
            if self.query_error:self.ret(0xd401);return
            at=x(2);occupied=self.blocked+[(p,p+n) for p,(_,n) in self.maps.items()]
            bounds=sorted({0,self.high,*[z for ab in occupied for z in ab]})
            assert 0<=at<self.high
            a=max(b for b in bounds if b<=at);b=min(b for b in bounds if b>at)
            kind=8 if any(a<=at<b for a,b in occupied) else 0
            vm.mem_write(x(0),struct.pack('<QQ6I',a,b-a,kind,0,0,0,0,0));self.ret()
        elif n in ('svcMapMemory','svcMapProcessCodeMemory'):
            assert self.locks==[self.symbols['g_VirtmemMutex']]
            if n=='svcMapMemory':dst,src,length=x(0),x(1),x(2);assert dst+length<=self.stack_end
            else:assert x(0)==0x1234;dst,src,length=x(1),x(2),x(3)
            assert self.low<=dst<dst+length<=self.high
            assert not (dst<self.heap_end and self.heap_low<dst+length)
            assert not any(dst<b and a<dst+length for a,b in self.blocked)
            assert src in self.allocations and self.allocations[src]==length
            assert any(a<=dst and dst+length<=a+n for a,n in self.reservations_live().values())
            self.map_calls+=1
            if self.map_calls==self.fail_map:self.ret(0xd401)
            else:vm.mem_map(dst,length);self.maps[dst]=(src,length);self.ret()
        elif n=='svcSetProcessMemoryPermission':
            assert self.locks==[self.symbols['g_VirtmemMutex']]
            assert x(0)==0x1234 and x(3)==3 and self.maps[x(1)][1]==x(2)
            self.permission_calls+=1
            if self.permission_calls==self.fail_permission:self.ret(0xd401)
            else:self.permissions[x(1)]=3;self.ret()
        elif n in ('svcUnmapMemory','svcUnmapProcessCodeMemory'):
            dst=x(1) if n=='svcUnmapProcessCodeMemory' else x(0)
            super().hook(vm,pc,size,user)
            if dst not in self.maps:self.permissions.pop(dst,None)
        elif n in ('diagAbortWithResult','abort'):raise AssertionError('Unexpected fatal '+n)
        else:super().hook(vm,pc,size,user)
    def add(self,begin,n):
        self.call('virtmemLock');p=self.call('virtmemAddReservation',begin,n);self.call('virtmemUnlock');assert p;return p
    def remove(self,p):
        self.call('virtmemLock');self.call('virtmemRemoveReservation',p);self.call('virtmemUnlock')
    def search(self,n,kind='virtmemFindCodeMemory',guard=PAGE):
        self.call('virtmemLock');p=self.call(kind,n,guard);self.call('virtmemUnlock');return p
    def clean(self):
        assert not self.maps and not self.permissions and not self.meta and not self.reservations_live()
        assert len(self.allocations)==1

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('elf',type=Path)
    ap.add_argument('--before',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    results=[]
    for path in (a.before,a.elf):
        m=Model(path);m.host();owners=m.fill_reserve();m.limit=MIB
        # Fill the stack window; leave a 40-MiB CPU mapping hole ABOVE it.
        # Force all random candidates into occupied space to test full search.
        hole=0xd0000000;end=hole+40*MIB
        m.blocked=[(0,hole),(end,m.high)];p=m.allocate(16*MIB)
        assert bool(p)==(path==a.elf),(path,p)
        if p:
            assert hole+PAGE<=p<p+16*MIB<=end-PAGE
            assert len(m.maps)==16 and m.permissions==dict.fromkeys(m.maps,3)
            m.check_bytes(p,16*MIB);m.release(p)
        else:assert not m.maps and len(m.allocations)==1
        assert m.random_calls>=512
        for ptr in owners:m.release(ptr)
        m.clean();results.append({'baseline':path==a.before,'recovered_16_mib':bool(p),
            'random_attempts':m.random_calls,'stack_end':m.stack_end,'available_hole_above_stack':hole})
    print('r5 exhausted-stack failure reproduced; r6 full-ASLR RW allocation succeeds',flush=True)

    m=Model(a.elf);m.host();m.full_reserve();m.limit=65536
    hole=0xd0000000;end=hole+64*MIB;m.blocked=[(0,hole),(end,m.high)]
    # An unmapped Wine reservation inside the hole must stay untouched.
    reserved=m.add(hole+8*MIB,24*MIB);p=m.allocate(17*MIB+123);assert p>=hole+32*MIB+PAGE
    m.check_bytes(p,17*MIB+123);m.release(p);m.remove(reserved);m.clean()
    # No new VA/RAM if there is truly no sufficiently large free span.
    m.blocked=[(0,hole),(hole+8*MIB,m.high)];assert not m.allocate(16*MIB);m.clean()
    # Keep earlier live allocations through a permission failure and rollback.
    m.blocked=[(0,hole),(end,m.high)];old=m.allocate(4*MIB);assert old;m.vm.mem_write(old,b'KEEP')
    m.fail_permission=m.permission_calls+3;assert not m.allocate(8*MIB)
    assert bytes(m.vm.mem_read(old,4))==b'KEEP' and len(m.maps)==64
    m.fail_permission=0;m.release(old);m.clean()
    # If rollback fails, retain pages/reservation. Never give a half-mapped
    # pointer to the caller, never free any still borrowed physical sources.
    m.fail_permission=m.permission_calls+3;m.fail_unmap=m.unmap_calls+3
    assert not m.allocate(8*MIB) and m.stats()[10]==1 and m.maps and m.meta

    # Exhaustive search property: compare exact first fit with an independent
    # small-page oracle, varying unsorted/overlapping software reservations,
    # kernel blocks, heap/alias exclusions, request size and guards.
    m=Model(a.elf);m.host();m.low=0x200000;m.high=m.stack_end=m.low+256*PAGE
    m.heap_low=m.low+20*PAGE;m.heap_end=m.low+32*PAGE;m.regions();m.rng=0
    m.vm.mem_write(m.symbols['g_AliasRegion'],struct.pack('<QQ',m.low+72*PAGE,m.low+88*PAGE))
    randomizer=random.Random(34591)
    for i in range(32):
        intervals=[(0,8)]+[(v:=randomizer.randrange(8,240),min(256,v+randomizer.randrange(1,17))) for _ in range(14)]
        m.blocked=[(m.low+x*PAGE,m.low+y*PAGE) for x,y in intervals[:8]]
        tokens=[m.add(m.low+x*PAGE,(y-x)*PAGE) for x,y in intervals[8:]]
        count=randomizer.randrange(1,25);guard=randomizer.randrange(0,4);expected=0
        forbidden=intervals+[(20,32),(72,88)]
        for x in range(guard,257-count-guard):
            if not any(x-guard<b and a<x+count+guard for a,b in forbidden):expected=m.low+x*PAGE;break
        p=m.search(count*PAGE,guard=guard*PAGE);assert p==expected,(i,p,expected)
        for t in reversed(tokens):m.remove(t)
    assert not m.call('virtmemFindCodeMemory',PAGE,PAGE),'Unlocked search must be rejected'
    assert not m.search(0) and not m.search(2**64-1) and not m.search(PAGE,guard=2**64-1)
    assert not m.meta
    m=Model(a.elf);m.host();m.full_reserve();m.limit=MIB;m.code_disabled=True
    m.blocked=[(0,0x30000000),(0x32000000,m.high)];p=m.allocate(16*MIB)
    assert p and p+16*MIB<0x32000000 and not m.permissions;m.release(p);m.clean()
    print('32 interval-oracle cases, real reservations, failure rollback, quarantine and bounds passed',flush=True)
    report={'passed':True,'hardware_tested':False,'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
        'baseline_elf_sha256':hashlib.sha256(a.before.read_bytes()).hexdigest(),'regressions':results,
        'checks':['Real linked old/new manager: stack exhausted, free high-ASLR hole, 512 random misses',
            'Only RW permissions, arbitrary fragment sizes, existing Wine reservations honored',
            'Single manager lock covers find, reservation, all maps and RW permission before publication',
            'Permission failure rollback retains earlier data; failed unmap quarantines storage',
            'True VA exhaustion fails cleanly; 32 oracle comparisons, guard/overflow/lock checks'],
        'sources':{n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in (
            'src/runtime/fextendo_virtmem.c','src/fex/horizon_scratch_pages.h','tests/fextendo_virtmem_binary.py',
            'tests/fextendo_fragmented_heap_binary.py','tests/fextendo_scratch_pages_binary.py')}}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
