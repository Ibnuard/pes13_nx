"""Execute actual FEX host callbacks under fragmented CPU-heap conditions.

Includes the logged 1-MiB lookup failure, arbitrary page-rounded requests,
private CRT alignment/header ownership, shared descriptor/byte bounds and
allocation failure without corrupting surviving buffers. Kernel/heap are
modeled; this does not validate the Horizon implementation on hardware.
"""
import argparse,hashlib,io,json,struct
from pathlib import Path
from fextendo_scratch_pages_binary import Model as Base,MIB,reg
PAGE=4096

class Model(Base):
    def __init__(self,path):
        # Symbol/relocation parsing makes many small random reads. Buffer the
        # exact ELF bytes so cold Windows files do not dominate test runtime.
        class Buffered:
            def __init__(self,data):self.data=data
            def open(self,mode):assert mode=='rb';return io.BytesIO(self.data)
        super().__init__(Buffered(path.read_bytes()));self.reservation_serial=0
    def hook(self,vm,pc,size,user):
        name=self.names.get(pc)
        if name=='virtmemAddReservation':
            assert self.locks==['vm']
            if self.no_reservation:self.ret(0)
            else:
                # The base single-buffer fixture used len(live) as its ID.
                # Mixed frees/reallocations must not overwrite a still-live
                # reservation just because there is a hole in that sequence.
                token=self.data+0x2000+self.reservation_serial*32
                self.reservation_serial+=1;assert token not in self.reservations
                self.reservations[token]=(vm.reg_read(reg(0)),vm.reg_read(reg(1)));self.ret(token)
        elif name=='malloc':
            n=vm.reg_read(reg(0));assert not self.locks
            if n>self.limit or self.fail_after==0:
                self.failed_allocations.append(n);self.ret(0)
            else:
                rounded=(n+PAGE-1)&-PAGE;p=self.next;self.next+=rounded+PAGE
                vm.mem_map(p,rounded);self.allocations[p]=rounded
                if self.fail_after is not None:self.fail_after-=1
                self.ret(p)
        else:super().hook(vm,pc,size,user)
    def host(self):
        super().host();table=self.call('pes13_fex_native_host')
        self.symbols['heap_allocate']=self.uq(table+72);self.symbols['heap_release']=self.uq(table+80)
    def heap(self,n,alignment):return self.call('heap_allocate',n,alignment)
    def heap_free(self,p):return self.call('heap_release',p)
    def full_reserve(self):return self.fill_reserve()+[self.allocate(8*MIB)]
    def check_bytes(self,p,n,tag=b'DATA'):
        for at in range(0,n-3,PAGE):self.vm.mem_write(p+at,tag)
        self.vm.mem_write(p+n-1,b'Z')
        for at in range(0,n-3,PAGE):
            if at+4<n:assert bytes(self.vm.mem_read(p+at,4))==tag
        assert bytes(self.vm.mem_read(p+n-1,1))==b'Z'
    def clean(self):assert not self.maps and not self.reservations and len(self.allocations)==1

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('elf',type=Path);ap.add_argument('--before',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    regressions=[]
    for path in (a.before,a.elf):
        m=Model(path);m.host();m.limit=64*1024;p=m.allocate(MIB)
        assert bool(p)==(path==a.elf)
        if p:
            assert len(m.maps)==16;m.check_bytes(p,MIB);m.release(p);m.clean()
        regressions.append({'case':'logged_lookup','request_bytes':MIB,'baseline':path==a.before,'succeeded':bool(p)})
        p=m.heap(3*MIB+123,65536)
        assert bool(p)==(path==a.elf)
        if p:
            assert p%65536==0;m.check_bytes(p,3*MIB+123);m.heap_free(p);m.clean()
        regressions.append({'case':'private_heap','request_bytes':3*MIB+123,'baseline':path==a.before,'succeeded':bool(p)})
        print('Baseline' if path==a.before else 'Candidate','lookup/private-heap regression passed',flush=True)
    m=Model(a.elf);m.host();owners=m.full_reserve();matrix=[]
    for limit in (PAGE,3*PAGE,64*1024,MIB):
        m.limit=limit
        for requested in (2*PAGE-1,135168,135169,MIB,MIB+135168,6225920,17*MIB+123):
            # Large/tiny-fragment combinations also run in the real-mapping
            # ASan/UBSan suite. Avoid quadratic Unicorn VM-map bookkeeping;
            # the ISA suite still exercises both large and 4-KiB cases.
            if limit<65536 and requested>MIB+135168:continue
            rounded=(requested+PAGE-1)&-PAGE;p=m.allocate(requested);assert p and p%PAGE==0
            assert len(m.maps)==0 if rounded<=limit else len(m.maps)>0
            m.check_bytes(p,requested);m.release(p);m.clean()
            matrix.append({'bytes':requested,'fragment_ceiling':limit})
        print('ARM64 size matrix passed, fragment ceiling',limit,flush=True)
    # More than eight small buffers; short-lived and long-lived users coexist.
    m.limit=PAGE;live=[m.allocate(2*PAGE) for _ in range(128)];assert all(live)
    assert not m.allocate(2*PAGE) and m.stats()[14]>0
    for i,p in enumerate(live):m.vm.mem_write(p,struct.pack('<I',i))
    for i in range(0,128,2):m.release(live[i])
    m.limit=65536
    mixed=[m.heap(MIB+73,65536) for _ in range(8)];assert all(mixed)
    for i in range(1,128,2):assert struct.unpack('<I',m.vm.mem_read(live[i],4))[0]==i;m.release(live[i])
    for p in mixed:m.heap_free(p)
    m.clean()
    print('128-owner exhaustion/mixed reuse passed',flush=True)
    # Private heap keeps its ABI-sized header and alignment even on an alias.
    m.limit=65536
    for requested,alignment in ((0,0),(1,16),(123,64),(4097,4096),(MIB+17,65536),(3*MIB+123,2*MIB)):
        p=m.heap(requested,alignment);assert p and p%max(alignment,16)==0
        raw,n=struct.unpack('<QQ',m.vm.mem_read(p-16,16));assert n==max(requested,1) and raw<=p-16
        m.check_bytes(p,n);m.heap_free(p);m.clean()
    assert not m.heap(12,24) and not m.heap(2**64-1,16) and not m.allocate(2**64-1)
    assert not m.allocate(128*MIB+1) # Explicit shared budget, no integer wrap.
    survivor=m.heap(MIB,16);assert survivor;m.vm.mem_write(survivor,b'KEEP')
    m.fail_after=2;assert not m.heap(2*MIB,16)
    assert bytes(m.vm.mem_read(survivor,4))==b'KEEP'
    m.fail_after=None;m.heap_free(survivor);m.clean()
    for p in owners:m.release(p)
    m.clean()
    report={'passed':True,'hardware_tested':False,'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
      'baseline_elf_sha256':hashlib.sha256(a.before.read_bytes()).hexdigest(),'regressions':regressions,'size_matrix':matrix,
      'checks':['Original 1-MiB lookup and private-heap failures reproduced; new callbacks recover both',
       f'{len(matrix)} arbitrary-size/fragment-ceiling combinations including 4-KiB fragmentation and non-power-of-two tails',
       '128 small owners, slot exhaustion, mixed CRT/scratch reuse and preserved live contents',
       'Zero-size, alignments 16 to 2 MiB, overflow and header/free ownership preserve ABI',
       'Partial allocation failure releases temporary pieces and preserves other live allocations'],
      'sources':{n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in ('tests/fextendo_fragmented_heap_binary.py','tests/fextendo_scratch_pages_binary.py')}}
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
