"""Check bounded memory timing and the linked ARM64 observer, not performance."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile
from fex_gap_probe import Model, reg

ROOT = Path(__file__).resolve().parents[1]


def native():
    code = r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <pthread.h>
#include <stdio.h>
#define R_SUCCEEDED(x) (!(x))
#define R_FAILED(x) (!!(x))
#define InfoType_ThreadTickCount 25
static int fex_gap_probe_enabled=1;
static __thread uint64_t wall=1000000000,cpu;
static __thread unsigned handle=44,producer;
static unsigned failed,queries,writes;
static uint64_t armGetSystemTick(void) { return wall; }
static uint64_t armTicksToNs(uint64_t v) { return v; }
static unsigned threadGetCurHandle(void) { return handle; }
static int svcGetInfo(uint64_t *out,unsigned kind,unsigned h,uint64_t sub) {
 assert(kind==25 && h==handle && sub==UINT64_MAX);
 __atomic_add_fetch(&queries,1,__ATOMIC_RELAXED);*out=cpu;return failed;
}
static void log_line(const char *fmt,...);
'''
    code += '#include "'+str(ROOT/'src/runtime/fex_memory_probe.h')+'"\n'
    code += r'''
static void log_line(const char *fmt,...) {
 assert(!producer && !pthread_mutex_trylock(&fex_memory_mutex));
 pthread_mutex_unlock(&fex_memory_mutex);(void)fmt;writes++;
}
static void sample(unsigned us,unsigned cpu_us) {
 uint64_t c,t=wine_nx_fex_memory_begin(&c);
 wall+=(uint64_t)us*1000;cpu+=(uint64_t)cpu_us*1000;
 wine_nx_fex_memory_end(t,c);
}
static void *worker(void *arg) {
 handle=(unsigned)(uintptr_t)arg;producer=1;sample(20000,7000);return 0;
}
int main(void) {
 producer=1;sample(100,50);assert(fex_memory_batch.calls==1 && !fex_memory_batch.count);
 sample(30000,29000);assert(fex_memory_batch.calls==2 && fex_memory_batch.count==1);
 struct fex_memory_sample s=fex_memory_batch.rows[0];
 assert(s.wall_us==30000 && s.cpu_us==29000 && s.cpu_valid && s.handle==44 && !writes);
 failed=1;sample(2000,1000);assert(!fex_memory_batch.rows[1].cpu_valid);failed=0;
 uint64_t c,t=wine_nx_fex_memory_begin(&c);wall+=2000000;failed=1;
 wine_nx_fex_memory_end(t,c);failed=0;assert(!fex_memory_batch.rows[2].cpu_valid);
 sample(2000,5000);assert(!fex_memory_batch.rows[3].cpu_valid);
 unsigned q=queries;fex_gap_probe_enabled=0;sample(10000,2000);assert(queries==q);
 fex_gap_probe_enabled=1;
 pthread_mutex_lock(&fex_memory_mutex);sample(2000,1000);pthread_mutex_unlock(&fex_memory_mutex);
 assert(fex_memory_dropped==1);
 for(unsigned i=0;i<40;i++)sample(2000,1000);
 assert(fex_memory_batch.count==32 && fex_memory_dropped==13);
 assert(fex_memory_batch.calls==45 && fex_memory_batch.cpu_valid_calls==42);
 producer=0;fex_memory_report();assert(writes==33 && !fex_memory_batch.calls && !fex_memory_dropped);
 pthread_t threads[8];for(unsigned i=0;i<8;i++)assert(!pthread_create(threads+i,0,worker,(void*)(uintptr_t)(80+i)));
 for(unsigned i=0;i<8;i++)assert(!pthread_join(threads[i],0));
 assert(fex_memory_batch.calls+fex_memory_dropped==8);
 for(unsigned i=0;i<fex_memory_batch.count;i++) {
  s=fex_memory_batch.rows[i];assert(s.wall_us==20000 && s.cpu_us==7000 && s.cpu_valid && s.handle>=80);
 }
 fex_memory_report();puts("PASS memory timing: ASan/UBSan, bounds, disable, failed counters, contention, concurrent producers");
}
'''
    with tempfile.TemporaryDirectory(prefix='fex-memory-') as d:
        p,exe=Path(d)/'check.c',Path(d)/'check';p.write_text(code)
        subprocess.run(['clang','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-pthread',
                        '-fsanitize=address,undefined','-fno-sanitize-recover=all',str(p),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True,timeout=30)


def main():
    if not __debug__:raise RuntimeError('Assertions required')
    p=argparse.ArgumentParser();p.add_argument('elf',type=Path);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();native()
    generated=a.source/'dlls/winevulkan/vulkan_thunks.c';text=generated.read_text()
    declarations='extern uint64_t wine_nx_fex_memory_begin(uint64_t *);\nextern void wine_nx_fex_memory_end(uint64_t, uint64_t);\n\n'
    assert text.count(declarations)==1
    stripped=text.replace(declarations,'')
    pattern=(r'    \{\n        uint64_t fex_memory_cpu;\n'
             r'        uint64_t fex_memory_begin = wine_nx_fex_memory_begin\(&fex_memory_cpu\);\n'
             r'(    vulkan_physical_device_from_handle\([^\n]+;)\n'
             r'        wine_nx_fex_memory_end\(fex_memory_begin, fex_memory_cpu\);\n    \}')
    stripped,n=re.subn(pattern,r'\1',stripped);assert n==4
    baseline=json.loads((ROOT/'local/fex3/fextendo/runtime/wine-patches.json').read_text())
    assert hashlib.sha256(stripped.encode()).hexdigest()==baseline['native-source']['dlls/winevulkan/vulkan_thunks.c']
    runtime=(a.source/'wine-nx-probe/source/runtime.c').read_text()
    assert (ROOT/'src/runtime/fex_memory_probe.h').read_text() in runtime
    m=Model(a.elf);ptr=m.data+256
    m.call('wine_nx_fex_memory_begin',ptr);begin=m.vm.reg_read(reg(0));cpu=struct.unpack('<Q',m.vm.mem_read(ptr,8))[0]
    m.now+=576000;m.cpu+=556800;m.call('wine_nx_fex_memory_end',begin,cpu)
    assert not m.logs and m.queries==2
    m.call('fex_memory_report');assert m.logs[0]==(1,30000,29000,1,30000),m.logs
    assert m.logs[1]==(begin,m.now,44,30000,1),m.logs
    m.vm.mem_write(m.symbols['fex_gap_probe_enabled'],struct.pack('<I',0))
    m.call('wine_nx_fex_memory_begin',ptr);assert m.vm.reg_read(reg(0))==0 and m.queries==2
    paths=['src/runtime/fex_memory_probe.h','tools/fex_memory_probe_patches.py','tests/fex_memory_probe.py',
           'tests/fex_gap_probe.py','tests/fex_samecore_binary.py','tests/fex_reservations.py']
    report={'passed':True,'hardware_tested':False,'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
            'checks':['Sanitizer observer bounds, concurrency, disabled and failed counters',
                      'Removing only four wrappers and declarations reproduces baseline thunk source exactly',
                      'Linked ARM64 reports 30ms wall / 29ms CPU, disabled path performs no CPU queries'],
            'source_hashes':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in paths},
            'generated_thunks_sha256':hashlib.sha256(generated.read_bytes()).hexdigest()}
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
