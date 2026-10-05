"""Execute original Rust shims, linked wrappers and CPU page recovery on ARM64.

Libc heap and Horizon services are modeled. No Rust shim, fallback, ownership,
copy/zero operation or wrapper is mocked. This is not a console shader test.
"""
import argparse,hashlib,io,json,struct,sys
from pathlib import Path
from elftools.elf.elffile import ELFFile
from fextendo_fragmented_heap_binary import Model as Base,MIB,PAGE,reg
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from fextendo_rust_heap_patches import PREFIX,SHIMS,NAK_SHA256

class Model(Base):
    def __init__(self,path):super().__init__(path);self.lock_calls=0
    def raw(self,n,a=16):
        assert not self.locks
        if n>self.limit or self.fail_after==0:self.failed_allocations.append(n);return 0
        p=(self.next+max(a,PAGE)-1)&-max(a,PAGE);rounded=(n+PAGE-1)&-PAGE
        self.next=p+rounded+PAGE;self.vm.mem_map(p,rounded);self.allocations[p]=rounded
        if self.fail_after is not None:self.fail_after-=1
        self.vm.mem_write(p,b'\xa5'*n);return p
    def hook(self,vm,pc,size,user):
        name=self.names.get(pc);x=lambda i:vm.reg_read(reg(i))
        if name=='mutexLock':self.lock_calls+=1
        if name=='malloc':self.ret(self.raw(x(0)))
        elif name=='calloc':
            n=x(0)*x(1);p=self.raw(n)
            if p:vm.mem_write(p,bytes(n))
            self.ret(p)
        elif name=='posix_memalign':
            out,a,n=x(0),x(1),x(2);p=self.raw(n,a)
            if p:vm.mem_write(out,struct.pack('<Q',p))
            self.ret(0 if p else 12)
        elif name=='realloc':
            old,n=x(0),x(1);assert old in self.allocations
            p=self.raw(n)
            if p:
                vm.mem_write(p,bytes(vm.mem_read(old,min(n,self.allocations[old]))))
                vm.mem_unmap(old,self.allocations.pop(old))
            self.ret(p)
        elif name=='memcpy':
            dst,src,n=x(0),x(1),x(2);vm.mem_write(dst,bytes(vm.mem_read(src,n)));self.ret(dst)
        elif name=='memset':
            dst,v,n=x(0),x(1),x(2);vm.mem_write(dst,bytes([v&255])*n);self.ret(dst)
        else:super().hook(vm,pc,size,user)
    def rust(self,fn,*args):return self.call('__wrap_'+PREFIX+SHIMS[fn][0],*args)

def linked_routes(path):
    with io.BytesIO(path.read_bytes()) as f:
        e=ELFFile(f);syms=list(e.get_section_by_name('.symtab').iter_symbols())
        addr={s.name:s['st_value'] for s in syms};funcs={s.name:(s['st_value'],s['st_size']) for s in syms if s['st_info']['type']=='STT_FUNC'}
        text=e.get_section_by_name('.text');data=text.data();start=text['sh_addr']
    routes={name:{'original':[],'wrapper':[]} for name in SHIMS}
    targets={}
    for name in SHIMS:
        sym=PREFIX+SHIMS[name][0]
        assert addr['__wrap_'+sym]==addr['pes13_rust_'+name] and addr[sym]!=addr['__wrap_'+sym]
        targets[addr[sym]]=(name,'original');targets[addr['__wrap_'+sym]]=(name,'wrapper')
    for i,(ins,) in enumerate(struct.iter_unpack('<I',data)):
        if ins&0x7c000000!=0x14000000:continue # B/BL immediate
        imm=ins&0x3ffffff
        if imm&0x2000000:imm-=0x4000000
        pc=start+4*i;target=pc+4*imm
        if target in targets:
            name,route=targets[target];routes[name][route].append(pc)
            if route=='original':
                assert any(a<=pc<a+n for fn,(a,n) in funcs.items() if fn.startswith('pes13_rust_')),('Rust call bypassed recovery',hex(pc),name)
    for name,r in routes.items():assert r['original'] and r['wrapper'],name
    return {n:{kind:len(pcs) for kind,pcs in r.items()} for n,r in routes.items()}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('elf',type=Path);ap.add_argument('--before',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    routes=linked_routes(a.elf)
    before=Model(a.before);before.host();before.limit=65536
    assert not before.call(PREFIX+SHIMS['alloc'][0],131077,64)
    m=Model(a.elf);m.host();owners=m.full_reserve();m.limit=65536;m.alias=0x2000001000
    p=m.rust('alloc',131077,64);assert p>2**32 and p%64==0;m.check_bytes(p,131077)
    m.rust('dealloc',p,131077,64);m.clean()
    for alignment in (1,16,64,4096,65536,2*MIB):
        p=m.rust('alloc',131077,alignment);assert p and not p%alignment
        m.check_bytes(p,131077);m.rust('dealloc',p,131077,alignment);m.clean()
    p=m.rust('alloc_zeroed',131077,64);assert p and not any(m.vm.mem_read(p,131077))
    m.vm.mem_write(p,b'KEEP');q=m.rust('realloc',p,131077,64,262177)
    assert q and bytes(m.vm.mem_read(q,4))==b'KEEP'
    m.fail_after=0;assert not m.rust('realloc',q,262177,64,524301)
    assert bytes(m.vm.mem_read(q,4))==b'KEEP';m.fail_after=None
    p=m.rust('realloc',q,262177,64,32768);assert p<2**32 and bytes(m.vm.mem_read(p,4))==b'KEEP'
    q=m.rust('realloc',p,32768,64,131077);assert q>2**32 and bytes(m.vm.mem_read(q,4))==b'KEEP'
    # An active alias must not add page-owner locks to ordinary allocator/free.
    locks=m.lock_calls
    for _ in range(20):
        normal=m.rust('alloc',123,16);m.rust('dealloc',normal,123,16)
    assert m.lock_calls==locks
    m.rust('dealloc',q,131077,64);m.clean()
    m.fail_map=m.map_calls+2;assert not m.rust('alloc',131077,64);m.fail_map=0;m.clean()
    report={'passed':True,'hardware_tested':False,'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
        'baseline_elf_sha256':hashlib.sha256(a.before.read_bytes()).hexdigest(),'libnak_rs_sha256':NAK_SHA256,'linked_routes':routes,
        'checks':['Pinned original Rust allocator fails under modeled fragmentation; linked candidate recovers the same request',
            'All direct Rust-shim call sites route through recovery; originals only called by reviewed wrappers',
            'Actual ARM64 Rust alloc/dealloc/realloc/zeroed ABI, alignments 1 to 2 MiB and aliases above 4 GiB',
            'Native to alias and alias to native growth/shrink preserve bytes; failed growth preserves original allocation',
            'Twenty ordinary alloc/free pairs acquire no page-owner lock with a live high alias',
            'Partial map failure rolls back fully'],
        'sources':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ('tests/fextendo_rust_heap_binary.py','tests/fextendo_fragmented_heap_binary.py','tests/fextendo_scratch_pages_binary.py','tools/fextendo_rust_heap_patches.py')}}
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
