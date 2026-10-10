"""Execute delivered ARM64 observer and NT dispatcher; kernel clocks/handlers modeled."""
import argparse,hashlib,json,struct
from pathlib import Path
from fextendo_silent import Model as BaseModel,reg
from fex_reservations import arm

class Model(BaseModel):
    def __init__(self,path):
        super().__init__(path)
        self.ms=100;self.expected_handler=0;self.expected_args=[];self.handler_calls=0
        self.kernel_queries=0;self.registry_busy=False;self.maintenance_rounds=0
        self.forbidden.update(self.symbols[n] for n in ('svcSetThreadActivity','svcGetThreadContext3','malloc','free') if n in self.symbols)
    def rows(self):
        return [struct.unpack('<IIIII4xQQQQ',self.vm.mem_read(self.symbols['fx_wait_rows']+56*i,56)) for i in range(128)]
    def hook(self,vm,pc,size,user):
        ins=struct.unpack('<I',vm.mem_read(pc,4))[0]
        if ins&~31 in (0xd53be020,0xd53be000):
            vm.reg_write(reg(ins&31),self.ms*19200 if ins&~31==0xd53be020 else 19200000)
            vm.reg_write(arm.UC_ARM64_REG_PC,pc+4);return
        if pc==self.expected_handler:
            self.handler_calls+=1
            values=[vm.reg_read(reg(i)) for i in range(8)]
            sp=vm.reg_read(arm.UC_ARM64_REG_SP)
            values += [struct.unpack('<Q',vm.mem_read(sp+8*i,8))[0] for i in range(max(0,len(self.expected_args)-8))]
            assert values==self.expected_args,(values,self.expected_args)
            active=[r for r in self.rows() if r[0]&3==1 and r[1]==0]
            assert bool(active)==self.expect_record
            if active:assert active[-1][7:]==tuple(values[:2]),active
            self.ret(0xc0000005);return
        if pc==self.symbols.get('threadGetCurHandle'):self.ret(0x99)
        elif pc==self.symbols.get('svcSleepThread'):
            self.maintenance_rounds+=1
            if self.maintenance_rounds>25:self.returned=True;vm.emu_stop()
            else:self.ms+=200;self.ret(0)
        elif pc==self.symbols.get('fx_debug_file_tick'):self.ret(0) # no SD write by the test
        elif pc==self.symbols.get('pthread_mutex_trylock'):self.ret(int(self.registry_busy))
        elif pc==self.symbols.get('pthread_mutex_unlock'):self.ret(0)
        elif pc==self.symbols.get('svcGetInfo'):
            self.kernel_queries+=1;assert vm.reg_read(reg(1)) in (25,0xf0000002)
            vm.mem_write(vm.reg_read(reg(0)),struct.pack('<Q',self.ms*100));self.ret(0)
        else:super().hook(vm,pc,size,user)
    def dispatch(self,arity,debug,excluded=False):
        self.call('fx_launch_debug_begin',int(debug));self.vm.mem_write(self.symbols['fx_wait_rows'],bytes(56*128))
        self.expected_args=[0x100000000+i for i in range(arity)]
        self.expected_handler=self.symbols['NtContinue'] if excluded else self.data+0xe000
        self.expect_record=debug and not excluded
        self.vm.mem_write(self.data+0x6000,struct.pack('<Q',self.expected_handler)*32)
        self.vm.mem_write(self.data+0x6200,bytes([arity*8])*32)
        self.vm.mem_write(self.symbols['KeServiceDescriptorTable'],struct.pack('<QQQ',self.data+0x6000,0,32)+struct.pack('<Q',self.data+0x6200))
        self.vm.mem_write(self.data+0x6400,struct.pack('<8Q',*(self.expected_args[8:]+[0]*(16-arity))))
        sp=self.stack+0xf000;self.vm.reg_write(arm.UC_ARM64_REG_SP,sp)
        self.vm.mem_write(sp,struct.pack('<QQ',self.expected_args[7],8))
        for i,value in enumerate([self.data+0x6400]+self.expected_args[:7]):self.vm.reg_write(reg(i),value)
        self.vm.reg_write(reg(30),self.stop);self.returned=False
        self.vm.emu_start(self.symbols['wine_nx_do_syscall'],0,count=200000)
        assert self.returned and self.vm.reg_read(reg(0))&0xffffffff==0xc0000005
        assert not any(r[0]&3 for r in self.rows())
        self.expected_handler=0
    def run_maintenance(self):
        self.maintenance_rounds=0;self.returned=False
        self.vm.reg_write(arm.UC_ARM64_REG_SP,self.stack+0xf000)
        self.vm.reg_write(reg(30),self.stop)
        self.vm.emu_start(self.symbols['log_flusher'],0,count=2000000)
        assert self.returned

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('elf',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();m=Model(a.elf)
    assert not m.call('wine_nx_wait_probe_begin',0,2,1,1)
    m.call('wine_nx_wait_probe_end',0,0);m.call('wine_nx_wait_probe_threads')
    assert not m.kernel_queries
    for arity,debug,excluded in ((8,False,False),(8,True,False),(16,True,False),(8,True,True)):
        m.dispatch(arity,debug,excluded)
    assert m.handler_calls==4
    m.call('fx_launch_debug_begin',1)
    token=m.call('wine_nx_wait_probe_begin',0,0x123,0xabc,0xdef);assert token
    m.call('wine_nx_wait_probe_end',token,0xc0000017)
    r=m.rows()[(token&0xffffffff)-1];assert r[0]&3==0 and r[4]==0xc0000017
    # Successful frame/audio calls recycle the ordinary ring; the one-off
    # error still has to appear in the next maintenance report.
    if 'fx_wait_errors' in m.symbols:
        for i in range(256):
            successful=m.call('wine_nx_wait_probe_begin',0,0x55,i,0)
            m.call('wine_nx_wait_probe_end',successful,0)
        assert not any(r[2]==0x123 for r in m.rows())
    stale=token;m.vm.mem_write(m.symbols['fx_wait_cursor'],struct.pack('<I',(token&0xffffffff)-1))
    token=m.call('wine_nx_wait_probe_begin',2,3,99,100);assert token!=stale
    m.call('wine_nx_wait_probe_end',stale,0);assert m.rows()[(token&0xffffffff)-1][0]&3==1
    m.registry_busy=True;m.run_maintenance()
    pending=bytes(m.vm.mem_read(m.symbols['fx_debug_pending'],64*1024))
    assert b'[WAIT-INFLIGHT] kind=vulkan code=3 thread=99' in pending
    assert b'[WAIT-CPU] registry busy; skipped' in pending
    if 'fx_wait_errors' in m.symbols:
        assert b'nt=123 thread=99 status=c0000017' in pending
        assert b'[WAIT-ERRORS]' in pending
        assert b'[ASSET-PIPES] object registry busy; snapshot skipped' in pending
        # If a producer reserves a serial but has not yet published its row,
        # maintenance must retry that row even without another failed call.
        deferred=m.call('wine_nx_wait_probe_begin',0,0x124,0xa4ec,0)
        m.call('wine_nx_wait_probe_end',deferred,0xc000000d)
        serial=struct.unpack('<Q',m.vm.mem_read(m.symbols['fx_wait_error_total'],8))[0]
        address=m.symbols['fx_wait_errors']+((serial-1)%64)*64
        state=struct.unpack('<I',m.vm.mem_read(address,4))[0]
        m.vm.mem_write(address,struct.pack('<I',state|2));m.run_maintenance()
        pending=bytes(m.vm.mem_read(m.symbols['fx_debug_pending'],64*1024))
        assert b'nt=124 thread=99 status=c000000d' not in pending
        m.vm.mem_write(address,struct.pack('<I',state));m.run_maintenance()
        pending=bytes(m.vm.mem_read(m.symbols['fx_debug_pending'],64*1024))
        assert b'nt=124 thread=99 status=c000000d' in pending
    m.call('wine_nx_wait_probe_end',token,0)
    m.registry_busy=False;m.call('wine_nx_wait_probe_threads')
    # Fill a real registry row and execute the CPU counter path, without any
    # thread-pause/context SVC or guest pointer reads being allowed.
    m.vm.mem_write(m.symbols['registry'],struct.pack('<IIc3xii4xQQQ',0x99,4,b'w',0,0,0,0,0))
    m.ms+=5000;m.call('wine_nx_wait_probe_threads');assert m.kernel_queries==1
    m.ms+=5000;m.call('wine_nx_wait_probe_threads');assert m.kernel_queries==2
    pending=bytes(m.vm.mem_read(m.symbols['fx_debug_pending'],64*1024))
    assert b'[WAIT-CPU] tid=4w thread=99 valid=1' in pending
    # Existing per-API counters identify a returning busy loop. Sampling its
    # completed record must retain the real failure status and scalar args.
    m.vm.mem_write(m.symbols['wine_nx_syscall_counts']+6*4,struct.pack('<I',430000))
    m.vm.mem_write(m.symbols['wine_nx_server_calls']+0x1d*4,struct.pack('<I',429000))
    m.sample_token=m.call('wine_nx_wait_probe_begin',0,6,0x2154,0)
    m.call('wine_nx_wait_probe_end',m.sample_token,0xc0000017)
    # Test a direct snapshot at the same instant instead of waiting 5s.
    assert 'fx_wait_call_summary' in m.symbols
    m.call('fx_wait_call_summary',m.ms)
    pending=bytes(m.vm.mem_read(m.symbols['fx_debug_pending'],64*1024))
    assert b'[WAIT-HOT] kind=nt code=6 calls=430000' in pending
    assert b'[WAIT-HOT] kind=server code=1d calls=429000' in pending
    assert b'[WAIT-RECENT] kind=nt code=6 thread=99 status=c0000017 samples=1 arg0=2154 arg1=0' in pending
    m.call('fx_launch_debug_begin',0);before=m.kernel_queries;m.run_maintenance();assert m.kernel_queries==before
    report={'passed':True,'hardware_tested':False,'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
        'checks':['Quiet observer and maintenance perform no diagnostic I/O or kernel queries',
          'Actual NT dispatcher preserves 8/16 arguments, 64-bit values and failure results',
          'Non-returning context syscall excluded; stale token cannot clear a reused slot',
          'Existing maintenance emits aged Vulkan entry to RAM only; busy registry skipped',
          'Existing API counters and recent return samples preserve failure status; no producer logging',
          'LW5 sticky NT failure survives 256 successful calls; busy pipe registry is skipped' if 'fx_wait_errors' in m.symbols else 'Pre-LW5 observer',
          'Real registry counters execute without thread suspension, context sampling or guest reads'],
        'sources':{n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in
           ('tests/fextendo_wait_probe_binary.py','src/runtime/fextendo_wait_probe.h','src/runtime/fextendo_wait_threads.h')}}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
