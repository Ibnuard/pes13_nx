"""Generated logger regression with real pthreads/ASan and linked ARM64 routing.

Kernel/stdio boundaries in the ARM64 test are modeled. No Switch FPS claim.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from unicorn import arm64_const as arm
from fex_reservations import Model as NativeModel, reg
from fex_resume_gate import function

ROOT = Path(__file__).resolve().parents[1]


def native(source):
    text = (source/'wine-nx-probe/source/runtime.c').read_text()
    pre = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <pthread.h>
#include <stdarg.h>
#include <string.h>
static int log_flusher_running=1, fex_jitlog_sync;
static __thread int producer;
static unsigned writes;
static char output[512];
static void log_line(const char* fmt,...) {
  assert(!producer); /* A normal timing producer must never reach stdio. */
  va_list args;va_start(args,fmt);vsnprintf(output,sizeof(output),fmt,args);va_end(args);
  writes++;
}
'''
    if 'fex_short_enqueue_text(msg)' in text:
        pre += 'static int fex_short_enqueue_text(const char *text){(void)text;return 0;}\n'
    pre += '#include "'+str(ROOT/'src/runtime/fex_jit_log_queue.h')+'"\n'
    pre += '#include "'+str(ROOT/'src/runtime/fex_warm_log.h')+'"\n'
    pre += 'static __thread int fex_log_metrics_batch;\n'+function(text,'fex_log_should_flush')
    body = r'''
static void* worker(void* arg) {
  producer=1;
  unsigned id=(unsigned)(uintptr_t)arg;
  char line[200];
  for(unsigned i=0;i<4000;i++) {
    snprintf(line,sizeof(line),"[FEX3-JIT] phase=compile_code uptime_ms=%u calls=%u",id,i);
    wine_nx_runtime_trace(line);
  }
  return 0;
}
static void* consumer(void* arg) {
  (void)arg;
  for(unsigned i=0;i<10000;i++) fex_jitlog_drain();
  return 0;
}
int main(void) {
  char line[512]="[FEX3-JIT] phase=compile_code uptime_ms=5 calls=1";
  assert(fex_log_should_flush(line,1,0)); /* Existing direct path forces SD flush. */
  producer=1;wine_nx_runtime_trace(line);producer=0;
  assert(!writes);memset(line,'x',sizeof(line));
  fex_jitlog_drain();assert(writes==1);
  assert(!strcmp(output,"[FEX3-JIT] phase=compile_code uptime_ms=5 calls=1"));
  const char* ordinary="[FEX3-JIT] phase=dispatch_compile uptime_ms=5 calls=1";
  pthread_mutex_lock(&fex_jitlog.mutex);
  producer=1;wine_nx_runtime_trace(ordinary);producer=0;
  pthread_mutex_unlock(&fex_jitlog.mutex);
  assert(fex_jitlog.dropped==1 && writes==1);
  for(unsigned i=0;i<FEX_JITLOG_SLOTS+1;i++) wine_nx_runtime_trace(ordinary);
  assert(fex_jitlog.count==FEX_JITLOG_SLOTS && fex_jitlog.dropped==2);
  fex_jitlog_drain();assert(!fex_jitlog.count && writes==33);
  const char* immediate[]={"[EXC] fault","[EXIT] end","[FEX3-JIT] FAIL",
    "[FEX3-JIT] phase=unknown calls=1","[FEX3-JIT] phase=compile_code_bad calls=1",
    "[FEX3-JIT] v1 init","[FEX3-FAULT] STOP"};
  for(unsigned i=0;i<sizeof(immediate)/sizeof(immediate[0]);i++) {
    unsigned old=writes;wine_nx_runtime_trace(immediate[i]);assert(writes==old+1);
  }
  memset(line,'a',sizeof(line));memcpy(line,ordinary,strlen(ordinary));line[511]=0;
  assert(fex_jitlog_enqueue(line));fex_jitlog_drain();assert(strlen(output)==511);
  char longline[513];memset(longline,'a',sizeof(longline));
  memcpy(longline,ordinary,strlen(ordinary));longline[512]=0;
  assert(!fex_jitlog_enqueue(longline));
  unsigned old=writes;
  log_flusher_running=0;wine_nx_runtime_trace(ordinary);assert(writes==old+1);
  log_flusher_running=1;fex_jitlog_sync=1;wine_nx_runtime_trace(ordinary);assert(writes==old+2);
  fex_jitlog_sync=0;
  uint64_t before=fex_jitlog.queued+fex_jitlog.dropped;
  pthread_t threads[8], reader;
  assert(!pthread_create(&reader,0,consumer,0));
  for(unsigned i=0;i<8;i++) assert(!pthread_create(&threads[i],0,worker,(void*)(uintptr_t)i));
  for(unsigned i=0;i<8;i++) assert(!pthread_join(threads[i],0));
  assert(!pthread_join(reader,0));fex_jitlog_drain();
  assert(fex_jitlog.queued+fex_jitlog.dropped-before==32000);
  assert(fex_jitlog.queued==fex_jitlog.written && !fex_jitlog.count);
  fex_jitlog_report();assert(strstr(output,"dropped="));
  puts("PASS 32000 concurrent producers, bounded/full/contended queue, owned text, immediate error/control paths");
}
'''
    code = pre + function(text, 'fex_jitlog_drain') + function(text, 'fex_jitlog_report')
    code += function(text, 'wine_nx_runtime_trace') + body
    with tempfile.TemporaryDirectory(prefix='fex-jitlog-') as tmp:
        p, exe = Path(tmp)/'test.c', Path(tmp)/'test'; p.write_text(code)
        subprocess.run(['clang','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror',
                        '-pthread','-fsanitize=address,undefined','-fno-sanitize-recover=all',
                        str(p),'-o',str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=30)


class Model(NativeModel):
    def __init__(self, path):
        super().__init__(path)
        self.direct, self.tries, self.unlocks, self.busy = 0, 0, 0, False

    def hook(self, vm, pc, size, user):
        s = self.symbols
        if pc == s.get('wine_nx_runtime_trace'):
            return  # Exercise the real bridge; base model normally stubs it.
        if pc == s.get('log_line'):
            self.direct += 1; self.ret()
        elif pc == s.get('pthread_mutex_trylock'):
            self.tries += 1; self.ret(16 if self.busy else 0)
        elif pc == s.get('pthread_mutex_unlock'):
            self.unlocks += 1; self.ret()
        elif pc == s.get('memcpy'):
            dst, src, n = [vm.reg_read(reg(i)) for i in range(3)]
            assert n <= 512
            vm.mem_write(dst, bytes(vm.mem_read(src,n))); self.ret(dst)
        else:
            super().hook(vm,pc,size,user)

    def trace(self, text, running=True, control=False, short=False):
        if "fex_short_enabled" in self.symbols:
            self.vm.mem_write(self.symbols["fex_short_enabled"],int(short).to_bytes(4,"little"))
        self.vm.mem_write(self.symbols['log_flusher_running'],int(running).to_bytes(4,'little'))
        if 'fex_jitlog_sync' in self.symbols:
            self.vm.mem_write(self.symbols['fex_jitlog_sync'],int(control).to_bytes(4,'little'))
        self.vm.mem_write(self.data,text.encode()+b'\0')
        self.returned=False
        self.vm.reg_write(arm.UC_ARM64_REG_SP,self.stack+0xf000)
        self.vm.reg_write(reg(30),self.stop); self.vm.reg_write(reg(0),self.data)
        self.vm.emu_start(self.symbols['wine_nx_runtime_trace'],0,count=30000)
        assert self.returned


def main():
    if not __debug__: raise RuntimeError('Assertions required')
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('elf',type=Path);ap.add_argument('--before',type=Path,required=True)
    ap.add_argument('--source',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();native(args.source)
    line='[FEX3-JIT] phase=compile_code uptime_ms=5000 calls=100'
    old=Model(args.before);old.trace(line);assert old.direct==1
    m=Model(args.elf);m.trace(line);assert m.direct==0 and m.tries==1 and m.unlocks==1
    m.busy=True;m.trace(line);assert m.direct==0 and m.tries==2 and m.unlocks==1
    m.busy=False
    for msg in ('[EXC] fault','[FEX3-JIT] v1 init','[FEX3-FAULT] STOP'):
        before=m.direct;m.trace(msg);assert m.direct==before+1
    before=m.direct;m.trace(line,running=False);m.trace(line,control=True);assert m.direct==before+2
    if 'fex_short_enabled' in m.symbols:
        for msg in ('[FEX3-JIT-THREAD] tid=4','[FEX3-JIT-SLOW] tid=4','[FEX3-JIT-CLOCK] origin_tick=1'):
            before=m.direct
            m.trace(msg,running=False,control=True,short=False)
            assert m.direct==before
            m.trace(msg,short=True)
            assert m.direct==before
    text=(args.source/'wine-nx-probe/source/runtime.c').read_text()
    flusher=function(text,'log_flusher')
    assert flusher.index('fex_log_metrics_batch = 1') < flusher.index('fex_jitlog_drain()') < flusher.index('fex_log_metrics_batch = 0')
    report={'passed':True,'hardware_tested':False,
            'native_elf_sha256':hashlib.sha256(args.elf.read_bytes()).hexdigest(),
            'before_native_elf_sha256':hashlib.sha256(args.before.read_bytes()).hexdigest(),
            'checks':['ASan/UBSan 32000 concurrent reports; bounded/full/busy queue, copied strings, 511/512 byte boundary',
                      'Generated error/unknown/startup and synchronous control paths preserved',
                      'Actual ARM64 trace route bypasses stdio for queued and busy normal JIT reports',
                      'Logger drains inside metrics batch, after producer unlock'],
            'generated_runtime_sha256':hashlib.sha256(text.encode()).hexdigest(),
            'source_hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                             (Path(__file__).resolve(),ROOT/'src/runtime/fex_jit_log_queue.h',ROOT/'tools/fex_jit_log_patches.py')}}
    args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
