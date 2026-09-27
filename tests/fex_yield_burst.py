"""Exercise generated C and linked ARM64 polling backoff; no device FPS claim."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from unicorn import arm64_const as arm
from fex_samecore_binary import Model as DelayModel, reg
from fex_resume_gate import function as extract_static

ROOT = Path(__file__).resolve().parents[1]


def function(text, name):
    return extract_static(text.replace('NTSTATUS WINAPI '+name+'(',
                                       'static NTSTATUS WINAPI '+name+'('), name)


def native(source):
    sync = (source/'dlls/ntdll/unix/sync.c').read_text()
    pre = r'''
#define __SWITCH__ 1
#define WINAPI
#define STATUS_SUCCESS 0
#include <assert.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>
typedef int NTSTATUS;
typedef uint64_t ULONGLONG;
typedef uintptr_t ULONG_PTR;
typedef struct { struct { uintptr_t UniqueThread; } ClientId; } TEB;
static __thread uint64_t now=1000000000, yield_cost, extra_pause;
static __thread unsigned yields, pauses, producer;
static __thread TEB teb;
static char output[24000];
static void log_line(const char *fmt, ...) {
  assert(!producer);
  va_list ap; va_start(ap,fmt);
  size_t n=strlen(output);
  int count=vsnprintf(output+n,sizeof(output)-n,fmt,ap);va_end(ap);
  assert(count>=0 && (size_t)count<sizeof(output)-n);
  strcat(output,"\n");
}
static uint64_t monotonic_counter(void) { return now; }
static TEB *NtCurrentTeb(void) { return &teb; }
static void svcSleepThread(int64_t ns) {
  if(ns==0) { ++yields;now+=yield_cost; }
  else { assert(ns==50000);++pauses;now+=500+extra_pause; }
}
'''
    pre += '#include "'+str(ROOT/'src/runtime/fex_yield_burst.h')+'"\n'
    pre += '#include "'+str(ROOT/'src/runtime/fex_yield_runtime.h')+'"\n'
    body = r'''
static void *worker(void *arg) {
  teb.ClientId.UniqueThread=(uintptr_t)arg;producer=1;
  for(unsigned i=0;i<128;i++) { now+=100;assert(NtYieldExecution()==0); }
  assert(yields==128 && pauses==2);
  producer=0;return 0;
}
int main(void) {
  struct fex_yield_burst b={0};
  for(unsigned i=0;i<63;i++) assert(!fex_yield_pause_due(&b,100+i*200,101+i*200));
  assert(fex_yield_pause_due(&b,12700,12701));
  assert(!b.count);
  /* Sparse calls, actual yielding, clock rollback, and a long stall reset. */
  for(unsigned i=0;i<1000;i++) assert(!fex_yield_pause_due(&b,50000+i*30000,50001+i*30000));
  for(unsigned i=0;i<1000;i++) assert(!fex_yield_pause_due(&b,50000+i*100,50020+i*100));
  assert(!fex_yield_pause_due(&b,90000,89999) && !b.count);
  b.first=99999;b.count=63;assert(!fex_yield_pause_due(&b,100,101) && b.count==1);
  b.first=100;b.count=63;assert(!fex_yield_pause_due(&b,20101,20102) && b.count==1);
  wine_nx_fex_yield_backoff=0;teb.ClientId.UniqueThread=4;
  for(unsigned i=0;i<1000;i++) NtYieldExecution();
  assert(yields==1000 && pauses==0);
  wine_nx_fex_yield_backoff=1;yields=0;
  for(unsigned i=0;i<63;i++) { now+=100;NtYieldExecution(); }
  assert(!pauses);NtYieldExecution();assert(pauses==1);
  yield_cost=20;
  for(unsigned i=0;i<1000;i++) NtYieldExecution();
  assert(pauses==1);
  yield_cost=0;extra_pause=30000;
  for(unsigned i=0;i<64;i++) { now+=100;NtYieldExecution(); }
  assert(pauses==2);
  pthread_t threads[8];
  for(unsigned i=0;i<8;i++) assert(!pthread_create(&threads[i],0,worker,(void*)(uintptr_t)(8+4*i)));
  for(unsigned i=0;i<8;i++) assert(!pthread_join(threads[i],0));
  fex_yield_report();
  assert(strstr(output,"tid=4 pauses=2 requested_us=100 actual_us=3100 peak_us=3050 late2ms=1"));
  assert(strstr(output,"tid=8 pauses=2 requested_us=100 actual_us=100"));
  output[0]=0;fex_yield_report();assert(!output[0]);
  for(unsigned i=40;i<=256;i+=4) wine_nx_fex_yield_pause_note(i,50);
  wine_nx_fex_yield_pause_note(260,50);assert(fex_yield_overflow==1);
  fex_yield_report();assert(strstr(output,"overflow=1"));
  puts("PASS: generated polling route, TLS isolation, sparse/productive yields, overflow, oversleep diagnostics");
}
'''
    with tempfile.TemporaryDirectory(prefix='fex-yield-') as tmp:
        p, exe = Path(tmp)/'test.c', Path(tmp)/'test'
        p.write_text(pre+function(sync,'NtYieldExecution')+body)
        subprocess.run(['clang','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror',
                        '-pthread','-fsanitize=address,undefined','-fno-sanitize-recover=all',
                        str(p),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True,timeout=30)


class Model(DelayModel):
    def __init__(self, path, enabled=True):
        super().__init__(path)
        self.mono=1000000000;self.yield_cost=0;self.extra_pause=0;self.notes=[]
        if 'wine_nx_fex_yield_backoff' in self.symbols:
            self.vm.mem_write(self.symbols['wine_nx_fex_yield_backoff'],struct.pack('<I',enabled))
        self.teb=self.data+0x9000;self.q(self.teb+0x48,164)

    def hook(self, vm, pc, size, user):
        s=self.symbols
        if pc==s.get('horizon_interrupt_time'): self.ret(self.mono)
        elif pc==s.get('svcSleepThread'):
            ns=vm.reg_read(reg(0));self.calls.append(ns)
            assert ns==0 or ns<=1000000000
            self.mono+=self.yield_cost if ns==0 else ns//100+self.extra_pause
            self.ret()
        elif pc==s.get('NtCurrentTeb'):self.ret(self.teb)
        elif pc==s.get('wine_nx_fex_yield_pause_note'):
            self.notes.append((vm.reg_read(reg(0)),vm.reg_read(reg(1))));self.ret()
        else:super().hook(vm,pc,size,user)

    def call(self, name='NtYieldExecution', timeout=0):
        self.returned=False
        self.vm.reg_write(arm.UC_ARM64_REG_SP,self.stack+0xf000)
        self.vm.reg_write(reg(30),self.stop);self.vm.reg_write(reg(0),0)
        self.vm.mem_write(self.data,struct.pack('<q',timeout));self.vm.reg_write(reg(1),self.data)
        self.vm.emu_start(self.symbols[name],0,count=100000)
        assert self.returned and self.vm.reg_read(reg(0)) & 0xffffffff == 0


def main():
    if not __debug__: raise RuntimeError('Assertions required')
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('elf',type=Path);ap.add_argument('--before',type=Path,required=True)
    ap.add_argument('--source',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();native(args.source)
    old=Model(args.before)
    for _ in range(128):old.call()
    assert old.calls==[0]*128
    new=Model(args.elf)
    for _ in range(63):new.mono+=100;new.call('NtDelayExecution')
    assert new.calls==[0]*63 and not new.notes
    # A second TLS context must not inherit the first thread's burst.
    new.tls+=0x3000;new.call();assert new.calls==[0]*64
    new.tls-=0x3000;new.call('NtDelayExecution')
    assert new.calls[-2:]==[0,50000] and new.notes==[(164,50)]
    new.extra_pause=30000
    for _ in range(64):new.call()
    assert new.notes[-1]==(164,3050)
    new.yield_cost=20;before=len(new.notes)
    for _ in range(128):new.call()
    assert len(new.notes)==before
    new.yield_cost=0
    for _ in range(128):new.mono+=30000;new.call()
    assert len(new.notes)==before
    control=Model(args.elf,False)
    for _ in range(128):control.call('NtDelayExecution')
    assert control.calls==[0]*128 and not control.notes
    relative=Model(args.elf)
    for timeout in (-1,-10000,-50000,-166667):
        relative.calls=[];relative.call('NtDelayExecution',timeout)
        assert relative.calls==[-timeout*100] and not relative.notes
    # Only the yield function changed; all delay branches, APC and clocks stay identical.
    baseline=Path('local/fex3/yield-burst/before/sync.c').read_text()
    generated=(args.source/'dlls/ntdll/unix/sync.c').read_text()
    assert function(baseline,'fex_delay_impl')==function(generated,'fex_delay_impl')
    assert function(baseline,'NtDelayExecution')==function(generated,'NtDelayExecution')
    files=['tests/fex_yield_burst.py','src/runtime/fex_yield_burst.h',
           'src/runtime/fex_yield_runtime.h','tools/fex_yield_burst_patches.py']
    report={'passed':True,'hardware_tested':False,
            'native_elf_sha256':hashlib.sha256(args.elf.read_bytes()).hexdigest(),
            'before_native_elf_sha256':hashlib.sha256(args.before.read_bytes()).hexdigest(),
            'checks':['Generated C ASan/UBSan: thresholds, sparse/productive yields, 8 pthreads/TLS, overflow and oversleep',
                      'Linked ARM64: 63 yields unchanged, 64th adds 50us, separate TLS, Sleep(0) and direct yield routes',
                      'Control bypass and positive-duration relative sleeps preserve kernel arguments',
                      'Alertable/infinite/absolute delay implementation unchanged; clocks untouched'],
            'source_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files},
            'generated_source_hashes':{p:hashlib.sha256((args.source/p).read_bytes()).hexdigest() for p in
                                      ['dlls/ntdll/unix/sync.c','wine-nx-probe/source/runtime.c']}}
    args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
