"""Execute the shipped ARM64 decoder setup and scratch pool under memory pressure.

NT/native allocation, clocks and locks are modeled. The actual DLL chooses
capacity, allocates/reuses/grows buffers and resets the compilation state.
"""
import argparse
import gc
import hashlib
import json
from pathlib import Path

from unicorn import arm64_const as arm
from fex_alloc import PARAM, reg
from fex_scratch import ScratchModel, DISOWN, FREE_ALL, OWNED

MIB=1024*1024
SETUP='_ZN7FEXCore8Frontend7Decoder30SetupDecodeInstructionsAtEntryEPNS_4Core19InternalThreadStateEyy'


class DecoderModel(ScratchModel):
    def __init__(self,dll,budget=128*MIB):
        self.budget=budget
        self.scratch_requests=[]
        self.objects=[]
        super().__init__(dll)
        self.sized=b'[FEX3-SCRATCH] v2 kit16' in dll.read_bytes()
        # Layout of this pinned build, confirmed by the loaded setup's stores.
        # An added size_t shifts fields after DecodedSize by eight bytes.
        self.decoded_offset=0x28
        self.maxinst_offset=0x88 if self.sized else 0x80
        self.thread=PARAM+0xd000
        self.frame=PARAM+0xd800
        self.gdt=PARAM+0xe800
        self.writeq(self.thread,self.frame)
        self.writeq(self.frame+0x4a0,self.gdt)

    def hook(self,vm,pc,size,user):
        if pc==self.scratch_alloc:
            requested=vm.reg_read(reg(0))
            self.scratch_requests.append(requested)
            rounded=(requested+4095)&-4096
            if sum(self.native_regions.values())+rounded>self.budget:
                vm.reg_write(reg(0),0)
                self.host_return()
                return
        super().hook(vm,pc,size,user)

    def decoder(self,default=128):
        obj=PARAM+0x3000+len(self.objects)*0x1000
        assert obj+0x900<self.thread
        self.vm.mem_write(obj,bytes(0x900))
        self.writeq(obj+0x18,self.ctx)
        self.vm.mem_write(self.ctx+0x4c,int(default).to_bytes(4,'little'))
        self.writeq(obj+0x30,self.pool)
        self.writeq(obj+0x38,128 if self.sized else 8*MIB)
        self.objects.append(obj)
        return obj

    def setup(self,obj,limit):
        self.invoke(SETUP,obj,self.thread,0x401000,limit)
        if self.trapped:return None
        pointer=self.readq(obj+self.decoded_offset)
        assert pointer and self.flag(obj+0x30)==OWNED
        assert self.readq(obj+self.maxinst_offset)==(limit or int.from_bytes(self.vm.mem_read(self.ctx+0x4c,4),'little'))
        if self.sized:
            effective=limit or int.from_bytes(self.vm.mem_read(self.ctx+0x4c,4),'little')
            assert self.readq(obj+0x68)==min(max(effective,1),65536)
        return pointer

    def disown_decoder(self,obj):self.invoke(DISOWN,obj+0x30)


def boundary_cases(dll):
    model=DecoderModel(dll)
    results=[]
    for limit,default in ((0,128),(0,0),(1,128),(128,128),(129,128),(500,128),(5000,128),(65536,128),((1<<64)-1,128)):
        obj=model.decoder(default)
        ptr=model.setup(obj,limit)
        assert ptr and not model.trapped
        requested=model.readq(obj+0x38)
        want=min(max(limit or default,1),65536)*128 if model.sized else 8*MIB
        assert requested==want,(limit,default,requested,want)
        # Live buffers must never be reused by another concurrently owned client.
        model.vm.mem_write(ptr,b'LIVE')
        model.vm.mem_write(ptr+want-4,b'LAST')
        results.append(dict(limit=limit,default=default,request_bytes=requested))
    pointers=[model.readq(obj+0x28) for obj in model.objects]
    assert len(set(pointers))==len(pointers)
    for obj,ptr,r in zip(model.objects,pointers,results):
        assert bytes(model.vm.mem_read(ptr,4))==b'LIVE'
        assert bytes(model.vm.mem_read(ptr+r['request_bytes']-4,4))==b'LAST'
        model.disown_decoder(obj)
    model.invoke(FREE_ALL,model.pool)
    assert not model.trapped and not model.native_regions
    del model;gc.collect()
    return results


def pressure(dll):
    model=DecoderModel(dll,budget=3*MIB)
    served=0
    for _ in range(8):
        ptr=model.setup(model.decoder(),0)
        if not ptr:break
        served+=1
    result=dict(served=served,stopped=model.trapped,bytes=sum(model.native_regions.values()),
                requests=model.scratch_requests)
    assert result['stopped']==(not model.sized)
    assert served==(8 if model.sized else 0)
    if model.sized:
        assert result['bytes']==8*16384
        for obj in model.objects:model.disown_decoder(obj)
        model.invoke(FREE_ALL,model.pool)
        assert not model.native_regions
    del model;gc.collect()
    return result


def growth(dll):
    model=DecoderModel(dll)
    obj=model.decoder()
    sizes=[]
    for limit in (1,128,5000,128,65536,500):
        ptr=model.setup(obj,limit)
        assert ptr and not model.trapped
        capacity=model.readq(obj+0x38)
        assert capacity==min(limit,65536)*128
        model.vm.mem_write(ptr+capacity-4,b'LAST')
        sizes.append(dict(limit=limit,requested=capacity,allocated=sum(model.native_regions.values())))
        model.disown_decoder(obj)
    # Another decoder can reclaim a disowned buffer without new backing.
    allocations=len(model.scratch_requests)
    other=model.decoder()
    assert model.setup(other,128)
    assert len(model.scratch_requests)==allocations
    model.disown_decoder(other)
    model.invoke(FREE_ALL,model.pool)
    assert not model.trapped and not model.native_regions
    return sizes


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('dll',type=Path);p.add_argument('--before',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    results={}
    for label,path in (('before',a.before),('candidate',a.dll)):
        results[label]=dict(boundaries=boundary_cases(path),pressure=pressure(path))
    results['growth_and_reuse']=growth(a.dll)
    files=[Path(__file__),*(Path('tests')/n for n in ('fex_scratch.py','fex_lookup.py','fex_memory.py','fex_alloc.py'))]
    report=dict(passed=True,hardware_tested=False,results=results,
        dll_sha256=hashlib.sha256(a.dll.read_bytes()).hexdigest(),
        baseline_dll_sha256=hashlib.sha256(a.before.read_bytes()).hexdigest(),
        sources={p.as_posix().split('/pes13-nx/')[-1]:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        scope=__doc__)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
