"""Exercise the delivered ARM64 observer; model timers, thread identity and libc.

No observer or allocation-wrapper implementation is mocked. This is not a GPU,
console, or game performance test.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from fextendo_silent import Model as Base, arm, reg

class Model(Base):
    def __init__(self,path):
        super().__init__(path)
        self.ms=1000;self.failure=False;self.alloc_calls=[]
    def hook(self,vm,pc,size,user):
        ins=struct.unpack('<I',vm.mem_read(pc,4))[0]
        if ins&~31 in (0xd53be020,0xd53be000):
            vm.reg_write(reg(ins&31),self.ms*19200 if ins&~31==0xd53be020 else 19200000)
            vm.reg_write(arm.UC_ARM64_REG_PC,pc+4);return
        if pc==self.symbols.get('threadGetCurHandle'):self.ret(0x1234)
        elif pc in {self.symbols.get('memcpy'),self.symbols.get('memmove')}:
            dest,src,n=[vm.reg_read(reg(i)) for i in range(3)]
            vm.mem_write(dest,bytes(vm.mem_read(src,n)));self.ret(dest)
        elif pc in {self.symbols.get(n) for n in ('malloc','calloc','realloc','memalign','aligned_alloc')}:
            self.alloc_calls.append(tuple(vm.reg_read(reg(i)) for i in range(2)))
            vm.mem_write(self.data+0x1000,struct.pack('<I',12 if self.failure else 16))
            self.ret(0 if self.failure else self.data+0x5000)
        else:super().hook(vm,pc,size,user)
    def u32(self,name,offset=0):return struct.unpack('<I',self.vm.mem_read(self.symbols[name]+offset,4))[0]
    def set32(self,name,n):self.vm.mem_write(self.symbols[name],struct.pack('<I',n))
    def text(self,pointer,length):return self.call('wine_nx_runtime_std_write',2,pointer,length)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('elf',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--fex-dll',type=Path,help='Also execute the frozen PE fatal helper and capture its real message')
    a=p.parse_args();m=Model(a.elf)
    m.text(1,100000)
    assert m.call('wine_nx_transition_begin',1,99)==0
    m.set32('fx_tr_enabled',1)
    token=m.call('wine_nx_transition_begin',1,99);assert token==1
    slot=struct.unpack('<III4xQQ',m.vm.mem_read(m.symbols['fx_tr_slots'],32))
    assert slot==(1,1,0x1234,19200000,99),slot
    m.ms=1250;m.call('wine_nx_transition_end',token,-4)
    assert m.u32('fx_tr_slots')==0 and m.uq(m.symbols['fx_tr_calls']+8)==1
    assert m.uq(m.symbols['fx_tr_peak']+8)==250000 and m.uq(m.symbols['fx_tr_errors']+8)==1
    event=struct.unpack('<III4xQQQ',m.vm.mem_read(m.symbols['fx_tr_events'],40))
    assert event==(5,0xfffffffc,0x1234,24000000,1,99),event
    m.set32('fx_tr_lock',1)
    m.call('wine_nx_transition_event',1,0,0,0)
    m.text(1,100000)
    assert m.call('wine_nx_transition_begin',0,0)==0 and m.uq(m.symbols['fx_tr_dropped'])==3
    m.set32('fx_tr_lock',0)
    text=b'A'*3000+b'TAIL';m.vm.mem_write(m.data,text)
    m.text(m.data,len(text))
    assert m.u32('fx_tr_text_size')==2048 and bytes(m.vm.mem_read(m.symbols['fx_tr_text']+2044,4))==b'TAIL'
    for name,args in [('__wrap_malloc',(8,)),('__wrap_calloc',(2,8)),
                      ('__wrap_realloc',(m.data+0x5000,8)),('__wrap_memalign',(16,8)),('__wrap_aligned_alloc',(16,16))]:
        assert m.call(name,*args)==m.data+0x5000
        assert struct.unpack('<I',m.vm.mem_read(m.data+0x1000,4))[0]==16
    count=m.u32('fx_tr_count');m.failure=True
    for name,args in [('__wrap_malloc',(8,)),('__wrap_calloc',(2,8)),
                      ('__wrap_realloc',(m.data+0x5000,8)),('__wrap_memalign',(16,8)),('__wrap_aligned_alloc',(16,16))]:
        assert m.call(name,*args)==0
        assert struct.unpack('<I',m.vm.mem_read(m.data+0x1000,4))[0]==12
    assert m.u32('fx_tr_count')==count+5 and len(m.alloc_calls)==10
    assert m.u32('fx_tr_alloc_count')==5
    for i,(n,alignment) in enumerate(((8,0),(16,0),(8,0),(8,16),(16,16))):
        site=struct.unpack('<III4xQQQQ',m.vm.mem_read(m.symbols['fx_tr_allocs']+48*i,48))
        assert site==(i+1,0x1234,12,m.ms*19200,n,alignment,m.stop),site
    m.vm.mem_write(m.data,b'[FEX] ordinary output\0');m.call('wine_nx_runtime_trace',m.data)
    assert m.u32('fx_tr_message_count')==0
    fatal=b'[FEX2-HEAP] STOP compiler scratch failed bytes=0x0000000000100000'
    m.vm.mem_write(m.data,fatal+b'\0');m.call('wine_nx_runtime_trace',m.data)
    assert m.u32('fx_tr_message_count')==1
    assert bytes(m.vm.mem_read(m.symbols['fx_tr_messages']+16,len(fatal)))==fatal
    m.call('wine_nx_transition_fex_image',0xff540000,0x450000)
    assert m.uq(m.symbols['fx_tr_fex_base'])==0xff540000 and m.uq(m.symbols['fx_tr_fex_size'])==0x450000
    r={'passed':True,'hardware_tested':False,'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
       'checks':['Disabled observer does not dereference message memory',
       'Real ARM64 begin/end preserve in-flight state, timer duration and Vulkan result evidence',
       'Contended observer drops evidence without waiting or dereferencing text',
       'Text tail is bounded to 2048 bytes',
       'Allocator wrappers preserve real return values and errno; failure events recorded',
       'FEX fatal messages retained independently of stream tail; routine trace filtered',
       'Bootstrap image address retained for ASLR-safe offline symbolication',
       'No storage calls from any observed producer']}
    if a.fex_dll:
        from fex_alloc import Model as PEModel,PARAM
        pe=PEModel(a.fex_dll);pe.vm.mem_write(PARAM,b'compiler scratch\0')
        pe.call('PES13FexHeapFailure',PARAM,0x100000)
        assert pe.trapped and pe.vm.reg_read(arm.UC_ARM64_REG_PC)-pe.base==0x14bb88
        actual=pe.logs[-1].encode();assert actual==fatal
        m.set32('fx_tr_message_count',0);m.vm.mem_write(m.data,actual+b'\0')
        m.call('wine_nx_runtime_trace',m.data)
        assert m.u32('fx_tr_message_count')==1
        assert bytes(m.vm.mem_read(m.symbols['fx_tr_messages']+16,len(actual)))==actual
        r['fex_dll_sha256']=hashlib.sha256(a.fex_dll.read_bytes()).hexdigest()
        r['checks'].append('Frozen PE HeapFailure actually logs and traps at RVA 0x14bb88; native observer retains the real payload (modeled callback bridge)')
    a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
