"""Run the delivered libnx pre-main path, with loader/kernel/services modeled.

The previous tests began at main(), missing heap allocation and applet/VI
setup. This executes __libnx_init, __libnx_initheap, __appInit and the PES
reservation wrapper. No real display, applet IPC or game is emulated.
"""
import argparse,hashlib,json,struct
from pathlib import Path
from fextendo_silent import Model as Base,reg

MIB=1024*1024

class Model(Base):
    def __init__(self,path,compatible=False,override=None,limit=64*MIB):
        super().__init__(path)
        self.info={12:0x200000,13:0xffe00000,3:0,6:3*1024**3} if compatible else {
            12:0x8000000,13:(1<<36)-0x8000000,3:0x180000000,6:442*MIB}
        self.override=override;self.limit=limit;self.query_error=False
        self.events=[];self.requests=[];self.reserved=[];self.exited=None;self.aborted=None
        self.simple={'newlibSetup','virtmemSetup','__libnx_init_thread','argvSetup',
                     'smInitialize','hidInitialize','timeInitialize','__libnx_init_time',
                     'fsInitialize','fsdevMountSdmc','__libnx_init_cwd','__nx_win_init',
                     '__libc_init_array','appletInitialize'}
        self.names={self.symbols[n]:n for n in self.simple if n in self.symbols}
    def hook(self,vm,pc,size,user):
        x=lambda i:vm.reg_read(reg(i))
        if pc==self.symbols.get('envSetup'):
            # The loader-supplied applet type remains authoritative.
            vm.mem_write(self.symbols['__nx_applet_type'],struct.pack('<I',2))
            self.events.append('envSetup');self.ret(0)
        elif pc==self.symbols.get('svcGetInfo'):
            self.events.append('query:'+str(x(1)))
            if self.query_error:self.ret(0xf601)
            else:vm.mem_write(x(0),struct.pack('<Q',self.info[x(1)]));self.ret(0)
        elif pc==self.symbols.get('envHasHeapOverride'):self.ret(self.override is not None)
        elif pc==self.symbols.get('envGetHeapOverrideAddr'):self.ret(self.override[0])
        elif pc==self.symbols.get('envGetHeapOverrideSize'):self.ret(self.override[1])
        elif pc==self.symbols.get('envGetExitFuncPtr'):self.ret(self.stop)
        elif pc==self.symbols.get('svcSetHeapSize'):
            self.events.append('heap');self.requests.append(x(1))
            if x(1)>self.limit:self.ret(0xc001)
            else:vm.mem_write(x(0),struct.pack('<Q',0x90000000));self.ret(0)
        elif pc==self.symbols.get('__nx_exit'):
            self.exited=x(0);self.returned=True;vm.emu_stop()
        elif pc==self.symbols.get('diagAbortWithResult'):
            self.aborted=x(0);self.returned=True;vm.emu_stop()
        elif pc==self.symbols.get('hosversionGet'):self.ret(0x150000)
        elif pc in self.names:
            self.events.append(self.names[pc]);self.ret(0)
        elif pc in {self.symbols.get('virtmemLock'),self.symbols.get('virtmemUnlock')}:self.ret(0)
        elif pc==self.symbols.get('svcQueryMemory'):
            assert x(2)==0x400000
            vm.mem_write(x(0),struct.pack('<QQ6I',0x200000,0xffe00000,0,0,0,0,0,0));self.ret(0)
        elif pc==self.symbols.get('virtmemAddReservation'):
            self.reserved.append((x(0),x(1)));self.ret(self.data+0x800)
        else:super().hook(vm,pc,size,user)
    def boot(self):
        self.call('__libnx_init',self.data,0x1234,self.stop)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('elf',type=Path)
    p.add_argument('--before',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    before=Model(a.before);before.boot()
    assert before.requests==[256*MIB] and before.aborted and 'appletInitialize' not in before.events
    m=Model(a.elf);m.boot()
    assert not m.aborted and m.exited is None and m.requests==[32*MIB] and not m.reserved
    assert m.events.index('query:12')<m.events.index('heap')<m.events.index('appletInitialize')<m.events.index('__nx_win_init')
    assert m.events[-1]=='__libc_init_array'
    assert [e for e in m.events if e.startswith('query:')]==['query:12','query:13','query:3','query:6']
    previous=len(m.events);m.call('wine_nx_launch_memory_compatible')
    assert len(m.events)==previous # cached once for this immutable process layout
    assert struct.unpack('<I',m.vm.mem_read(m.symbols['__nx_applet_type'],4))[0]==2
    assert m.uq(m.symbols['fake_heap_start'])==0x90000000 and m.uq(m.symbols['fake_heap_end'])==0x92000000
    for limit,expected in ((16*MIB,[32*MIB,16*MIB]),(2*MIB,[32*MIB,16*MIB,8*MIB,4*MIB,2*MIB])):
        m=Model(a.elf,limit=limit);m.boot()
        assert m.requests==expected and not m.aborted and m.exited is None
    m=Model(a.elf,limit=0);m.boot()
    assert not m.aborted and m.exited==0xc001 and 'appletInitialize' not in m.events
    m=Model(a.elf,compatible=True,limit=512*MIB);m.boot()
    assert m.requests==[256*MIB] and m.reserved==[(0x400000,0x189a000)] and m.exited is None
    for compatible in (False,True):
        override=(0x40000000,2*1024**3)
        m=Model(a.elf,compatible=compatible,override=override,limit=0);m.boot()
        assert not m.requests and not m.aborted and m.exited is None
        assert m.uq(m.symbols['fake_heap_start'])==override[0]
        assert m.uq(m.symbols['fake_heap_end'])==sum(override)
        assert bool(m.reserved)==compatible
    m=Model(a.elf);m.query_error=True;m.boot()
    assert m.requests==[32*MIB] and not m.reserved and not m.aborted
    m=Model(a.elf,override=(0xfffffffffffff000,0x2000));m.boot()
    assert m.exited is not None and not m.aborted and 'appletInitialize' not in m.events
    report={'passed':True,'hardware_tested':False,
        'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
        'baseline_elf_sha256':hashlib.sha256(a.before.read_bytes()).hexdigest(),
        'checks':['Real libnx pre-main path queries memory before heap, applet and VI setup',
          'Old 256-MiB startup aborts under modeled low applet allowance; new rejection boot uses 32 MiB with bounded fallback',
          'Unsupported/query-failed modes skip the fixed PES image reservation and retain the loader applet type',
          'Valid 32-bit no-alias retains the default heap and fixed image reservation',
          'Loader-owned heaps are never resized; invalid heap or failed allocation returns to loader without fatal abort'],
        'sources':{'tests/fextendo_startup_binary.py':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
