"""Execute real old/new ARM64 delay paths and sanitize generated wait-age report."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from unicorn import arm64_const as arm
from fex_samecore_binary import Model as DelayModel, reg
from fex_resume_gate import function


class Model(DelayModel):
    def hook(self, vm, pc, size, user):
        s = self.symbols
        if pc == s.get('svcSleepThread'):
            raw = vm.reg_read(reg(0))
            ns = raw if raw < 1 << 63 else raw - (1 << 64)
            self.calls.append(ns)
            if self.stop_after and len(self.calls) >= self.stop_after:
                vm.emu_stop()
                return
            if ns <= 0: self.mono += self.yield_cost
            elif self.early and len(self.calls) == 1: self.mono += ns//200
            else: self.mono += (ns+99)//100 + self.overshoot
            self.mono &= (1 << 64)-1
            self.ret()
        elif pc == s.get('horizon_interrupt_time'):
            self.ret(self.mono)
        elif pc in {s.get('gettimeofday'), s.get('NtQuerySystemTime')}:
            self.wall_reads += 1
            wall = 116444736000000000 + self.mono
            if self.wall_reads > 1: wall += self.wall_jump
            if pc == s.get('NtQuerySystemTime'): self.q(vm.reg_read(reg(0)),wall)
            else:
                seconds, sub = divmod(wall-116444736000000000,10000000)
                vm.mem_write(vm.reg_read(reg(0)),struct.pack('<qq',seconds,sub//10))
            self.ret()
        else: super().hook(vm,pc,size,user)

    def delay(self, timeout, *, yield_cost=0, wall_jump=0, early=False, overshoot=0,
              start=1000000000, stop_after=0):
        self.calls, self.returned = [],False
        self.mono, self.wall_reads = start,0
        self.yield_cost, self.wall_jump = yield_cost,wall_jump
        self.early, self.overshoot, self.stop_after = early,overshoot,stop_after
        self.vm.reg_write(arm.UC_ARM64_REG_SP,self.stack+0xf000)
        self.vm.reg_write(reg(30),self.stop)
        self.vm.reg_write(reg(0),0)
        self.vm.mem_write(self.data,struct.pack('<q',timeout))
        self.vm.reg_write(reg(1),self.data)
        self.vm.emu_start(self.symbols['NtDelayExecution'],0,count=100000)
        assert self.returned or (stop_after and len(self.calls)==stop_after), 'Unbounded delay'
        if self.returned: assert self.vm.reg_read(reg(0)) & 0xffffffff == 0
        return (self.mono-start) & ((1<<64)-1)


def wait_report(source):
    text = (source/'dlls/ntdll/unix/horizon.c').read_text()
    a=text.index('struct fex_resume_waiter {')
    b=text.index('static void fex_resume_wake_locked',a)
    declarations=text[a:b]
    report=function(text,'wine_nx_fex_resume_report')
    pre=r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <pthread.h>
struct horizon_server_object { struct { unsigned tid, suspend; } thread; };
static pthread_mutex_t horizon_server_objects_mutex=PTHREAD_MUTEX_INITIALIZER;
static uint64_t tick;
static uint64_t horizon_interrupt_time(void) { return tick; }
static char output[8192];
void wine_nx_runtime_trace(const char* text) {
  assert(strlen(output)+strlen(text)+2<sizeof(output));
  strcat(output,text); strcat(output,"\n");
}
'''
    body=r'''
int main(void) {
  struct horizon_server_object objects[17]={0};
  struct fex_resume_waiter waiters[17]={0};
  for(unsigned i=0;i<17;i++) {
    objects[i].thread.tid=60+i*4; objects[i].thread.suspend=1;
    waiters[i].object=&objects[i];waiters[i].parked_at=1000;
    waiters[i].next=i+1<17?&waiters[i+1]:0;
  }
  fex_resume_waiters=waiters; fex_resume_counts.active=17;
  tick=1000+600000000; wine_nx_fex_resume_report();
  assert(strstr(output,"tid=60 suspend=1 parked_us=60000000"));
  assert(strstr(output,"tid=120 ") && !strstr(output,"tid=124 "));
  output[0]=0; tick+=100000000; wine_nx_fex_resume_report();
  assert(strstr(output,"tid=60 suspend=1 parked_us=70000000"));
  for(unsigned i=0;i<17;i++) assert(objects[i].thread.suspend==1);
  fex_resume_waiters=0; fex_resume_counts.active=0;
  output[0]=0;wine_nx_fex_resume_report();assert(!strstr(output,"[FEX3-WAIT]"));
  output[0]=0;wine_nx_fex_resume_report();assert(!output[0]);
}
'''
    with tempfile.TemporaryDirectory(prefix='fex-sleep-wait-') as d:
        cpp,exe=Path(d)/'test.c',Path(d)/'test'
        cpp.write_text(pre+declarations+report+body)
        subprocess.run(['clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
                        '-pthread','-fsanitize=address,undefined','-fno-sanitize-recover=all',
                        str(cpp),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True,timeout=30)


def main():
    if not __debug__: raise RuntimeError('Assertions required')
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('elf',type=Path);ap.add_argument('--before',type=Path,required=True)
    ap.add_argument('--source',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    old,new=Model(args.before),Model(args.elf)
    # A runnable peer consumes 25ms during the redundant zero-duration yield.
    red=old.delay(-50000,yield_cost=250000)
    green=new.delay(-50000,yield_cost=250000)
    assert red==250000 and green==50000 and new.calls==[5000000]
    # A 100ms wall-clock correction must not lengthen a relative 5ms sleep.
    red_wall=old.delay(-50000,wall_jump=-1000000)
    green_wall=new.delay(-50000,wall_jump=-1000000)
    assert red_wall==1050000 and green_wall==50000 and new.wall_reads==0
    checks=[]
    for duration in (1,7,10,10000,50000,166667,36000050000):
        assert new.delay(-duration)==duration
        assert all(0<ns<=3600000000000 for ns in new.calls)
        assert sum(new.calls)==duration*100 and new.wall_reads==0
        checks.append({'relative_100ns':duration,'kernel_sleeps_ns':new.calls[:]})
    assert new.delay(-50000,early=True)==50000 and new.calls==[5000000,2500000]
    assert new.delay(-50000,overshoot=90000)==140000 and len(new.calls)==1
    assert new.delay(-50000,start=(1<<64)-20000)==50000
    for model in (old,new):
        assert model.delay(0)==0 and model.calls==[0]
        expired=116444736000000000+1000000000-1
        assert model.delay(expired)==0 and model.calls==[0]
        future=116444736000000000+1000000000+50000
        assert model.delay(future)==50000 and model.calls==[0,5000000]
    new.delay(-(1<<63),stop_after=1)
    assert new.calls==[3600000000000], 'INT64_MIN must not overflow to a yield'
    wait_report(args.source)
    # Alertable and infinite branches are byte-for-byte source-identical;
    # execute the modified nonalertable path, rather than emulate APC delivery.
    before=(Path('local/fex3/sleep-deadline/before/sync.c')).read_text()
    after=(args.source/'dlls/ntdll/unix/sync.c').read_text()
    split='        LARGE_INTEGER now;\n        timeout_t when, diff;'
    assert function(before,'fex_delay_impl').split(split)[0]==function(after,'fex_delay_impl').split(split)[0]
    report={'passed':True,'hardware_tested':False,
            'native_elf_sha256':hashlib.sha256(args.elf.read_bytes()).hexdigest(),
            'before_native_elf_sha256':hashlib.sha256(args.before.read_bytes()).hexdigest(),
            'modeled_peer_delay_us':{'before':red//10,'after':green//10},
            'modeled_wall_adjustment_us':{'before':red_wall//10,'after':green_wall//10},
            'relative_cases':checks,
            'checks':['Real ARM64 delay: no extra yield/wall reads for relative waits',
                      'Early wake, oversleep, counter wrap, hourly chunk, INT64_MIN conversion',
                      'Zero/absolute delay behavior preserved; alertable/infinite source branches unchanged',
                      'ASan/UBSan generated waiter report: 60s/70s ages, 16-row bound, no count changes'],
            'scope':'Fault-injected clock/scheduler model, not measured Switch delay or gameplay',
            'source_hashes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                             [Path(__file__),Path('src/runtime/fex_relative_delay.h'),Path('tools/fex_sleep_patches.py')]}}
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
