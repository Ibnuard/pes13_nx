"""Check bounded gap records and actual ARM64 observer; cache use needs hardware."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile
from fex_samecore_binary import Model as BaseModel, reg, arm

ROOT=Path(__file__).resolve().parents[1]


def native(source):
    pre=r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#define R_SUCCEEDED(x) (!(x))
#define InfoType_ThreadTickCount 25
static __thread uint64_t wall=1000000000,cpu;
static __thread unsigned handle=44,producer;
static unsigned failed,queries,writes;
static uint64_t armGetSystemTick(void) { return wall; }
static uint64_t armTicksToNs(uint64_t t) { return t; }
static unsigned threadGetCurHandle(void) { return handle; }
static int svcGetInfo(uint64_t *out,unsigned kind,unsigned h,uint64_t sub) {
  assert(kind==25 && h==handle && sub==UINT64_MAX);
  __atomic_add_fetch(&queries,1,__ATOMIC_RELAXED);*out=cpu;return failed;
}
static void log_line(const char *fmt,...);
'''
    pre+='#include "'+str(ROOT/'src/runtime/fex_gap_probe.h')+'"\n'
    body=r'''
static void log_line(const char *fmt,...) {
  assert(!producer);assert(pthread_mutex_trylock(&fex_gaps.mutex)==0);
  pthread_mutex_unlock(&fex_gaps.mutex);(void)fmt;writes++;
}
static void step(unsigned us,unsigned cpu_us) { wall+=(uint64_t)us*1000;cpu+=(uint64_t)cpu_us*1000;fex_gap_present(1,2,1); }
static void *worker(void *arg) {
  handle=(unsigned)(uintptr_t)arg;producer=1;
  fex_gap_present(1,2,1);step(100000,5000);producer=0;return 0;
}
int main(void) {
 producer=1;fex_gap_present(1,2,1);step(16667,5000);assert(!fex_gaps.count);
 fex_gap_pipeline_note(1,4000);fex_gap_pipeline_note(3,6000);step(100000,10000);
 assert(!writes && fex_gaps.count==1);
 struct fex_gap_sample s=fex_gaps.rows[0];
 assert(s.wall_us==100000 && s.cpu_us==10000 && s.cpu_valid && s.handle==44);
 assert(s.pipeline_us[1]==4000 && s.pipeline_us[3]==6000);
 failed=1;step(100000,10000);assert(!fex_gaps.rows[1].cpu_valid);
 failed=0;step(100000,10000);assert(!fex_gaps.rows[2].cpu_valid);
 step(100000,10000);assert(fex_gaps.rows[3].cpu_valid && !fex_gaps.rows[3].pipeline_us[1]);
 unsigned n=fex_gaps.count;wall+=100000000;fex_gap_present(8,9,1);assert(fex_gaps.count==n);
 fex_gap_present(8,9,0);wall+=100000000;fex_gap_present(8,9,1);assert(fex_gaps.count==n);
 unsigned q=queries;fex_gap_probe_enabled=0;step(100000,10000);assert(queries==q);
 fex_gap_probe_enabled=1;fex_gap_present(1,2,0);fex_gap_present(1,2,1);
 pthread_mutex_lock(&fex_gaps.mutex);step(100000,10000);pthread_mutex_unlock(&fex_gaps.mutex);
 assert(fex_gaps.dropped==1 && fex_gaps.count==n);
 for(unsigned i=0;i<40;i++)step(100000,10000);
 assert(fex_gaps.count==32 && fex_gaps.dropped==13);
 producer=0;fex_gap_report();assert(!fex_gaps.count && !fex_gaps.dropped && writes==33);
 pthread_t t[8];for(unsigned i=0;i<8;i++)assert(!pthread_create(&t[i],0,worker,(void*)(uintptr_t)(80+i)));
 for(unsigned i=0;i<8;i++)assert(!pthread_join(t[i],0));
 assert(fex_gaps.count+fex_gaps.dropped==8);
 for(unsigned i=0;i<fex_gaps.count;i++)assert(fex_gaps.rows[i].cpu_us==5000 && fex_gaps.rows[i].wall_us==100000);
 fex_gap_report();puts("PASS sanitizer gap records, TLS isolation, bounded overflow, failed counters, stream reset and disable");
}
'''
    with tempfile.TemporaryDirectory(prefix='fex-gap-') as tmp:
        p,exe=Path(tmp)/'gap.c',Path(tmp)/'gap';p.write_text(pre+body)
        subprocess.run(['clang','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-pthread',
                        '-fsanitize=address,undefined','-fno-sanitize-recover=all',str(p),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True,timeout=30)


class Model(BaseModel):
    def __init__(self,path):
        super().__init__(path);self.now=192000000;self.cpu=0;self.queries=0;self.logs=[]
        self.log_addrs={v for k,v in self.symbols.items() if k=='log_line' or k.startswith('log_line.')}

    def hook(self,vm,pc,size,user):
        s=self.symbols;ins=int.from_bytes(vm.mem_read(pc,4),'little')
        if ins & ~31 == 0xd53be020:
            if ins & 31 != 31:vm.reg_write(reg(ins & 31),self.now)
            vm.reg_write(arm.UC_ARM64_REG_PC,pc+4)
        elif pc==s.get('svcGetInfo'):
            assert vm.reg_read(reg(1))==25 and vm.reg_read(reg(2))==44
            self.q(vm.reg_read(reg(0)),self.cpu);self.queries+=1;self.ret()
        elif pc==s.get('threadGetCurHandle'):self.ret(44)
        elif pc in {s.get('pthread_mutex_trylock'),s.get('pthread_mutex_unlock')}:self.ret()
        elif pc in self.log_addrs:
            self.logs.append(tuple(vm.reg_read(reg(i)) for i in range(1,6)));self.ret()
        else:super().hook(vm,pc,size,user)

    def call(self,name,*args):
        self.returned=False;self.vm.reg_write(arm.UC_ARM64_REG_SP,self.stack+0xf000)
        self.vm.reg_write(reg(30),self.stop)
        for i,v in enumerate(args):self.vm.reg_write(reg(i),v)
        self.vm.emu_start(self.symbols[name],0,count=150000);assert self.returned

    def present(self):self.call('wine_nx_fex_frame_note',1,2,self.now-100,0,0,0,0)


def environments(source,elf):
    text=(source/'wine-nx-probe/source/runtime.c').read_text()
    for name in ('runtime_environment','fex_jit_large_environment','fex_jit_small_environment'):
        for disk in (False,True):
            symbol=name+('_disk' if disk else '')
            # Semicolons can occur inside PATH; use the ending quote+semicolon.
            match=re.search(r'static const char '+symbol+r'\[\] =\n(.*?";)',text,re.S)
            strings=re.findall(r'"(?:[^"\\]|\\.)*"',match[1])
            data=b''.join(ast.literal_eval('b'+v) for v in strings)+b'\0'
            assert data in elf.read_bytes(),symbol
            entries=data.rstrip(b'\0').split(b'\0');keys=[e.split(b'=')[0].lower() for e in entries]
            assert keys==sorted(keys) and len(keys)==len(set(keys))
            options=dict(e.split(b'=',1) for e in entries)
            assert options[b'FEX_MAXINST']==(b'5000' if 'large' in name else b'128' if 'small' in name else b'500')
            assert options[b'FEX_DISKCACHE']==(b'1' if disk else b'0')
            if disk:
                assert options[b'FEX_APP_CACHE_LOCATION']==b'C:\\fex-jit-cache\\'
                assert options[b'FEX_DISKCACHEFILEMAPPING']==options[b'FEX_DISKCACHEANONCACHING']==options[b'FEX_DISKCACHEMEMORYSIZE']==b'0'
                assert options[b'FEX_DISKCACHEMAXFILESIZE']==b'67108864' and b'FEX_DISKCACHEPATH' not in options
    assert '"/fex_diskcache", 0)' in text


def main():
    if not __debug__:raise RuntimeError('Assertions required')
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('elf',type=Path)
    ap.add_argument('--source',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();native(a.source);environments(a.source,a.elf)
    m=Model(a.elf);m.present();m.now+=1920000;m.cpu+=192000;m.present()
    assert m.queries==2 and not m.logs
    m.call('fex_gap_report');assert m.logs[0][1:]==(44,100000,1,10000),m.logs
    m.vm.mem_write(m.symbols['fex_gap_probe_enabled'],struct.pack('<I',0));m.present();assert m.queries==2
    paths=['tests/fex_gap_probe.py','tests/fex_samecore_binary.py','tests/fex_reservations.py',
           'src/runtime/fex_gap_probe.h','tools/fex_gap_probe_patches.py']
    report={'passed':True,'hardware_tested':False,'disk_cache_persistence_verified':False,
            'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
            'checks':['ASan/UBSan gap observer: TLS, bounds, contention, failed counters, reset and off control',
                      'Linked ARM64 real Present-note path reports 100ms wall vs 10ms presenting-thread CPU; no producer logs',
                      'Six sorted UTF8 environment blocks found in ELF; cache off default, on settings bounded; maxinst control retained'],
            'source_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
            'generated_source_hashes':{'wine-nx-probe/source/runtime.c':hashlib.sha256((a.source/'wine-nx-probe/source/runtime.c').read_bytes()).hexdigest()}}
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
