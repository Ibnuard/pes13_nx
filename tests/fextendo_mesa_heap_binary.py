"""Execute the real Mesa allocator that failed in the r4 console log.

Only libc and Horizon services are modeled. Mesa ralloc/linear/GC functions,
recovery wrappers, ownership and byte copying execute linked ARM64 code.
"""
import argparse,hashlib,json,struct
from pathlib import Path
from fextendo_rust_heap_binary import Model as Base,MIB,PAGE,reg

class Model(Base):
    def hook(self,vm,pc,size,user):
        name=self.names.get(pc)
        if name=='malloc_usable_size':self.ret(self.allocations[vm.reg_read(reg(0))])
        else:super().hook(vm,pc,size,user)
    def context(self,bound):
        root=self.call('ralloc_context',0);assert root
        self.vm.mem_write(self.data+0x500,struct.pack('<I',bound*144))
        p=self.call('linear_context_with_opts',root,self.data+0x500)
        return root,p

def main():
    ap=argparse.ArgumentParser();ap.add_argument('elf',type=Path);ap.add_argument('--before',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    regressions=[]
    for path in (a.before,a.elf):
        m=Model(path);m.host();owners=m.full_reserve();m.limit=65536
        root,ctx=m.context(621)
        assert bool(ctx)==(path==a.elf),(path,ctx)
        assert 90192 in m.failed_allocations
        if ctx:
            p=m.call('linear_alloc_child',ctx,144);assert p
            m.check_bytes(p,144)
            for _ in range(6):
                child=m.call('linear_alloc_child',ctx,32000);assert child;m.check_bytes(child,32000)
            assert m.stats()[3]>0
        else:
            # Calling the actual next instruction with the failed context
            # recreates the r4 NULL read, not an arbitrary simulated crash.
            try:m.call('linear_alloc_child',0,144)
            except AssertionError as e:assert 'linear_alloc_child' in str(e)
            else:raise AssertionError('Expected r4 NULL-context access')
        m.call('ralloc_free',root);m.clean()
        regressions.append({'baseline':path==a.before,'spirv_bound':621,'failed_malloc_bytes':90192,'recovered':bool(ctx)})
    m=Model(a.elf);m.host();owners=m.full_reserve();m.limit=65536
    for bound in (17,621,2048,8193):
        root,ctx=m.context(bound);assert ctx
        p=m.call('linear_alloc_child',ctx,bound+7);m.check_bytes(p,bound+7)
        m.call('ralloc_free',root);m.clean()
    # Recursive tree free must route both alias and normal allocations.
    parent=m.call('ralloc_context',0)
    child=m.call('ralloc_size',parent,32768);assert child
    grandchild=m.call('ralloc_size',child,90123);assert grandchild
    m.vm.mem_write(child,b'KEEP');m.vm.mem_write(grandchild,b'CHILD')
    grown=m.call('reralloc_size',parent,child,256*1024+73);assert grown
    assert bytes(m.vm.mem_read(grown,4))==b'KEEP'
    assert m.call('ralloc_parent',grandchild)==grown
    m.fail_after=0
    assert not m.call('reralloc_size',parent,grown,512*1024+17)
    assert bytes(m.vm.mem_read(grown,4))==b'KEEP' and m.call('ralloc_parent',grandchild)==grown
    m.fail_after=None
    shrunk=m.call('reralloc_size',parent,grown,1024);assert shrunk
    assert bytes(m.vm.mem_read(shrunk,4))==b'KEEP' and m.call('ralloc_parent',grandchild)==shrunk
    m.call('ralloc_free',parent);m.clean()
    # Reuse idle reserve pages when mappings/sources are unavailable. This
    # path also serves the unchanged Rust wrappers via the shared broker.
    for p in owners:m.release(p)
    m.limit=0
    for n in (1,90192,135177,1048583):
        p=m.call('pes13_mesa_malloc',n);assert p and m.call('pes13_cpu_pages_owned',p)
        assert m.call('pes13_cpu_pages_size',p)==n
        m.check_bytes(p,n);m.call('pes13_mesa_free',p);m.clean()
    # Several loans share pages while live FEX compiler memory stays intact.
    held=m.allocate(16*MIB);m.vm.mem_write(held,b'LIVE')
    loans=[m.call('pes13_mesa_malloc',4097+i) for i in range(48)];assert all(loans)
    for i,p in enumerate(loans):m.vm.mem_write(p,struct.pack('<I',i))
    for i,p in enumerate(loans):assert struct.unpack('<I',m.vm.mem_read(p,4))[0]==i;m.call('pes13_mesa_free',p)
    assert bytes(m.vm.mem_read(held,4))==b'LIVE';m.release(held);m.clean()
    m.limit=65536
    locks=m.lock_calls
    for _ in range(20):
        p=m.call('pes13_mesa_malloc',111);p=m.call('pes13_mesa_realloc',p,333);assert p
        m.call('pes13_mesa_free',p)
    assert m.lock_calls==locks,'Normal path added allocator locks'
    assert not m.call('pes13_mesa_malloc',2**64-1)
    report={'passed':True,'hardware_tested':False,'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
        'baseline_elf_sha256':hashlib.sha256(a.before.read_bytes()).hexdigest(),'regressions':regressions,
        'checks':['Reproduced actual r4 90,192-byte malloc failure and linear allocator NULL read; candidate completes same calls',
          'Variable SPIR-V bounds and buffer growth recover through actual Mesa C functions',
          'Recursive tree ownership, native/alias realloc, child reparenting, failed growth and complete release',
          'Reserve loans for arbitrary sizes; 48 mixed native CPU owners preserve live FEX compiler contents',
          'Ordinary malloc/realloc/free perform no fallback ownership locks; overflow rejected'],
        'sources':{n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in ('tests/fextendo_mesa_heap_binary.py','tests/fextendo_rust_heap_binary.py','tests/fextendo_fragmented_heap_binary.py','tests/fextendo_scratch_pages_binary.py')}}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
