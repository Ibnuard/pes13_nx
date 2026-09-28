"""Test adaptive polling on generated C and linked ARM64, including old control."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from fex_yield_burst import Model as BurstModel, function, reg

ROOT=Path(__file__).resolve().parents[1]


def native(source):
    sync=(source/'dlls/ntdll/unix/sync.c').read_text()
    pre=r'''
#define __SWITCH__ 1
#define WINAPI
#define STATUS_SUCCESS 0
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <pthread.h>
typedef int NTSTATUS;
typedef uint64_t ULONGLONG;
typedef uintptr_t ULONG_PTR;
typedef struct { struct { uintptr_t UniqueThread; } ClientId; } TEB;
static __thread uint64_t now=1000000000, yield_cost, extra_pause;
static __thread unsigned yields, pauses, producer;
static __thread TEB teb;
static char output[10000];
static void log_line(const char *fmt, ...) {
  assert(!producer);va_list ap;va_start(ap,fmt);size_t n=strlen(output);
  int count=vsnprintf(output+n,sizeof(output)-n,fmt,ap);va_end(ap);
  assert(count>=0 && (size_t)count+2<sizeof(output)-n);strcat(output,"\n");
}
static uint64_t monotonic_counter(void) { return now; }
static TEB *NtCurrentTeb(void) { return &teb; }
static void svcSleepThread(int64_t ns) {
  if(!ns) { yields++;now+=yield_cost; }
  else { assert(ns==50000);pauses++;now+=500+extra_pause; }
}
'''
    for header in ('fex_yield_burst.h','fex_yield_adaptive.h','fex_yield_runtime.h','fex_yield_adaptive_runtime.h'):
        pre+='#include "'+str(ROOT/'src/runtime'/header)+'"\n'
    body=r'''
static void *worker(void *arg) {
  producer=1;teb.ClientId.UniqueThread=(uintptr_t)arg;
  for(unsigned i=0;i<512;i++) { now+=100;assert(!NtYieldExecution()); }
  assert(yields==512 && pauses==12);producer=0;return 0;
}
static int burst(struct fex_yield_adaptive *s, uint64_t *t, unsigned calls) {
  int result=0;
  for(unsigned i=0;i<calls;i++) {
    *t+=100;result=fex_yield_adaptive_due(s,*t,*t+1);
    if(i+1<calls)assert(!result);
  }
  return result;
}
int main(void) {
  struct fex_yield_adaptive s={0};uint64_t t=1000000;
  for(unsigned i=0;i<4;i++) {
    assert(burst(&s,&t,64)==1);
    assert(!fex_yield_adaptive_complete(&s,t+1,t+501));t+=501;
  }
  assert(burst(&s,&t,32)==2);
  assert(!fex_yield_adaptive_complete(&s,t+1,t+1501));t+=1501;
  assert(s.heat==0 && !s.cooling);assert(burst(&s,&t,64)==1);
  assert(fex_yield_adaptive_complete(&s,t+1,t+3001));t+=3001;
  uint64_t end=t;
  for(unsigned i=0;i<499;i++) { t+=100;assert(!fex_yield_adaptive_due(&s,t,t+1)); }
  assert(t-end==49900 && s.cooling);
  t=end+50000;assert(!fex_yield_adaptive_due(&s,t,t+1) && !s.cooling);
  assert(burst(&s,&t,63)==1);
  /* Tight individual calls spread over too long a burst do not qualify. */
  s=(struct fex_yield_adaptive){0};
  for(unsigned i=0;i<1000;i++) { t+=500;assert(!fex_yield_adaptive_due(&s,t,t+1)); }
  s.heat=4;s.count=31;s.first=t;
  assert(!fex_yield_adaptive_due(&s,t+1,t+21) && !s.heat && !s.count);
  s.heat=4;s.count=31;s.first=t;s.last=t;
  assert(!fex_yield_adaptive_due(&s,t+30000,t+30001) && !s.heat);
  assert(!fex_yield_adaptive_due(&s,t,t-1) && !s.count);
  s.heat=4;s.last=t;
  assert(!fex_yield_adaptive_due(&s,t-2,t-1) && !s.heat);
  /* Generated function and actual counter implementation with concurrent TLS. */
  wine_nx_fex_yield_backoff=wine_nx_fex_yield_adaptive=1;
  pthread_t threads[8];
  for(unsigned i=0;i<8;i++)assert(!pthread_create(&threads[i],0,worker,(void*)(uintptr_t)(4+4*i)));
  for(unsigned i=0;i<8;i++)assert(!pthread_join(threads[i],0));
  fex_yield_report();fex_yield_adaptive_report();
  assert(strstr(output,"initial=32 sustained=64 cooldowns=0"));
  assert(strstr(output,"tid=4 pauses=12 requested_us=600 actual_us=600"));
  output[0]=0;fex_yield_adaptive_report();assert(!output[0]);
  wine_nx_fex_yield_adaptive=0;
  for(unsigned i=0;i<512;i++)NtYieldExecution();assert(pauses==8);
  wine_nx_fex_yield_backoff=0;pauses=0;
  for(unsigned i=0;i<512;i++)NtYieldExecution();assert(!pauses);
  puts("PASS generated adaptive routing/TLS; conservative startup, sustained polling, sparse/productive yields, cooldown and controls");
}
'''
    with tempfile.TemporaryDirectory(prefix='fex-adaptive-') as tmp:
        p,exe=Path(tmp)/'test.c',Path(tmp)/'test';p.write_text(pre+function(sync,'NtYieldExecution')+body)
        subprocess.run(['clang','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-pthread',
                        '-fsanitize=address,undefined','-fno-sanitize-recover=all',str(p),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True,timeout=30)


class Model(BurstModel):
    def __init__(self,path,enabled=True,adaptive=True):
        super().__init__(path,enabled);self.adaptive_notes=[]
        if 'wine_nx_fex_yield_adaptive' in self.symbols:
            self.vm.mem_write(self.symbols['wine_nx_fex_yield_adaptive'],struct.pack('<I',adaptive))

    def hook(self,vm,pc,size,user):
        if pc==self.symbols.get('wine_nx_fex_yield_adaptive_note'):
            self.adaptive_notes.append((vm.reg_read(reg(0)),vm.reg_read(reg(1))));self.ret()
        else:super().hook(vm,pc,size,user)

    def poll(self,n,name='NtDelayExecution',gap=100):
        for _ in range(n):self.mono+=gap;self.call(name)


def main():
    if not __debug__:raise RuntimeError('Assertions required')
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('elf',type=Path);ap.add_argument('--before',type=Path,required=True)
    ap.add_argument('--source',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();native(args.source)
    old=Model(args.before);old.poll(512);assert len(old.notes)==8
    new=Model(args.elf);new.poll(256)
    assert len(new.notes)==4 and new.adaptive_notes==[(0,0)]*4
    new.poll(31);assert len(new.notes)==4
    new.poll(1,'NtYieldExecution');assert len(new.notes)==5 and new.adaptive_notes[-1]==(1,0)
    # Another TLS context starts at 64 despite the first context being hot.
    new.tls+=0x3000;new.poll(32);assert len(new.notes)==5
    new.tls-=0x3000;new.extra_pause=3000;new.poll(32)
    assert new.adaptive_notes[-1]==(1,1) and new.notes[-1]==(164,350)
    count=len(new.notes);new.extra_pause=0;new.poll(499)
    assert len(new.notes)==count
    new.poll(1);new.poll(62);assert len(new.notes)==count
    new.poll(1);assert len(new.notes)==count+1 and new.adaptive_notes[-1]==(0,0)
    new.yield_cost=20;count=len(new.notes);new.poll(128);assert len(new.notes)==count
    new.yield_cost=0;new.poll(128,gap=30000);assert len(new.notes)==count
    control=Model(args.elf,adaptive=False);control.poll(512)
    assert control.calls==old.calls and control.notes==old.notes and not control.adaptive_notes
    off=Model(args.elf,enabled=False);off.poll(512);assert off.calls==[0]*512 and not off.notes
    relative=Model(args.elf)
    for timeout in (-1,-10000,-50000,-166667):
        relative.calls=[];relative.call('NtDelayExecution',timeout)
        assert relative.calls==[-timeout*100] and not relative.notes
    generated=args.source/'dlls/ntdll/unix/sync.c'
    before=ROOT/'local/fex3/yield-adaptive/before/sync.c'
    for name in ('fex_delay_impl','NtDelayExecution'):
        assert function(before.read_text(),name)==function(generated.read_text(),name)
    files=['tests/fex_yield_adaptive.py','tests/fex_yield_burst.py','tests/fex_samecore_binary.py',
           'src/runtime/fex_yield_burst.h','src/runtime/fex_yield_runtime.h',
           'src/runtime/fex_yield_adaptive.h','src/runtime/fex_yield_adaptive_runtime.h',
           'tools/fex_yield_adaptive_patches.py']
    report={'passed':True,'hardware_tested':False,
            'native_elf_sha256':hashlib.sha256(args.elf.read_bytes()).hexdigest(),
            'before_native_elf_sha256':hashlib.sha256(args.before.read_bytes()).hexdigest(),
            'before_sync_sha256':hashlib.sha256(before.read_bytes()).hexdigest(),
            'checks':['Generated C ASan/UBSan and 8 pthreads: four initial pauses, adaptive threshold, TLS, reset/cooldown, counters',
                      'Actual ARM64 Sleep(0)/yield route, oversleep cooldown, productive/sparse yields, separate TLS',
                      'Same-binary adaptive=0 reproduces old syscall sequence; backoff=0 gives plain yields',
                      'Relative sleep syscall durations unchanged; alertable/infinite/absolute delay implementation identical'],
            'source_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files},
            'generated_source_hashes':{p:hashlib.sha256((args.source/p).read_bytes()).hexdigest() for p in
                                      ['dlls/ntdll/unix/sync.c','wine-nx-probe/source/runtime.c']}}
    args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
