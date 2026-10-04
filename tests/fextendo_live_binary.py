"""Execute delivered ARM64 thread snapshots; model only libnx/kernel locks.

Verify resume sequencing and context ABI without guest or filesystem calls.
This does not emulate Horizon scheduling or measure device pause overhead.
"""
import argparse,hashlib,json,struct
from pathlib import Path
from fextendo_silent import Model as Base,arm,reg

class Model(Base):
    def __init__(self,path):
        super().__init__(path)
        self.held=set();self.paused=set();self.events=[];self.context_error=0
        self.contended=None;self.resume_failures=0;self.tick_calls=0;self.legacy=False
        self.forbidden.update(self.symbols[n] for n in ('malloc','calloc','realloc','memalign','aligned_alloc',
            '__wrap_malloc','pthread_mutex_lock','svcSleepThread','wine_nx_runtime_trace',
            'mutexLock') if n in self.symbols)
    def hook(self,vm,pc,size,user):
        s=self.symbols;ins=struct.unpack('<I',vm.mem_read(pc,4))[0]
        arg=lambda i:vm.reg_read(reg(i))
        if ins&~31 in (0xd53be020,0xd53be000):
            vm.reg_write(reg(ins&31),38400000 if ins&~31==0xd53be020 else 19200000)
            vm.reg_write(arm.UC_ARM64_REG_PC,pc+4);return
        if pc==s.get('threadGetCurHandle'):self.ret(99)
        elif pc==s.get('envIsSyscallHinted'):
            assert arg(0) in (0x32,0x33);self.ret(1)
        elif pc==s.get('pthread_mutex_trylock'):
            address=arg(0);assert not self.paused
            if address==self.contended:self.ret(16)
            else:
                assert address not in self.held;self.held.add(address);self.ret(0)
        elif pc==s.get('pthread_mutex_unlock'):
            assert not self.paused;self.held.remove(arg(0));self.ret(0)
        elif pc==s.get('svcGetInfo'):
            assert not self.paused and self.held=={s['profile_mutex']}
            assert arg(2)==42 and arg(3)==0xffffffffffffffff
            self.tick_calls+=1
            if self.legacy and self.tick_calls%2:self.ret(7)
            else:vm.mem_write(arg(0),struct.pack('<Q',123456));self.ret(0)
        elif pc==s.get('svcSetThreadActivity'):
            handle,activity=arg(0),arg(1);assert handle==42 and self.held=={s['profile_mutex']}
            self.events.append(('pause' if activity else 'resume',handle))
            if activity:
                assert not self.paused;self.paused.add(handle);self.ret(0)
            else:
                assert self.paused=={handle}
                if self.resume_failures:self.resume_failures-=1;self.ret(2)
                else:self.paused.remove(handle);self.ret(0)
        elif pc==s.get('svcGetThreadContext3'):
            assert self.paused=={42} and self.held=={s['profile_mutex']} and arg(1)==42
            self.events.append(('read',42))
            # libnx ThreadContext: 29 GPRs then FP, LR, SP, PC at 0x100.
            values=[0x1000+i for i in range(29)]+[0x80001000,0xabcdef,0x80000000,0x12345678]
            vm.mem_write(arg(0),struct.pack('<33Q',*values));self.ret(self.context_error)
        else:super().hook(vm,pc,size,user)
    def snapshot(self):
        self.call('wine_nx_live_threads_snapshot',self.data)
        assert not self.held and not self.paused
        header=struct.unpack('<4IQ',self.vm.mem_read(self.data,24))
        row=struct.unpack('<7I4x12Q',self.vm.mem_read(self.data+24,128))
        return header,row

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('elf',type=Path)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();m=Model(a.elf)
    # Native registry includes its own maintenance thread; never pause self.
    for i,handle in enumerate((99,42)):
        m.vm.mem_write(m.symbols['registry']+48*i,struct.pack('<IIb3xii4xQQQ',handle,handle+100,ord('w'),0,0,0,0,0))
    header,row=m.snapshot()
    assert header[:4]==(0,1,1,0),header
    assert row==(42,142,ord('w'),0,0,0,0,123456,0x12345678,0xabcdef,0x80000000,0x80001000,
                 0x1000,0x1001,0x1002,0x1003,0x1013,0x1014,0x101c),row
    assert m.events==[('pause',42),('read',42),('resume',42)]
    m.context_error=3;m.events=[];header,row=m.snapshot()
    assert row[5]==3 and row[6]==0 and row[8]==0 and m.events[-1]==('resume',42)
    m.context_error=0;m.resume_failures=1;m.events=[];m.snapshot()
    assert m.events==[('pause',42),('read',42),('resume',42),('resume',42)]
    for name,status in [('profile_mutex',1),('registry_mutex',2)]:
        m.contended=m.symbols[name];m.events=[];header,row=m.snapshot()
        assert header[0:2]==(status,0) and not m.events
    m.contended=None;m.legacy=True;m.tick_calls=0;header,row=m.snapshot()
    assert m.tick_calls==2 and row[3]==0 and row[7]==123456
    root=Path(__file__).resolve().parents[1]
    result={'passed':True,'hardware_tested':False,'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
            'checks':['ARM64 context layout and CPU-tick result preserved; maintenance thread excluded',
            'Each successful pause has immediate resume even after failed read; one retry on resume error',
            'Profile lifetime guard held and registry released throughout kernel observations',
            'Contended locks skip without waiting; legacy tick fallback works',
            'No file writes, allocations, blocking locks, sleeps or Wine/FEX callbacks'],
            'sources':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in
                ('src/runtime/fextendo_live_threads.h','src/runtime/fextendo_live_trace.h','tests/fextendo_live_binary.py')}}
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
