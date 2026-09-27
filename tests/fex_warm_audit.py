"""Exercise generated warmup observers and routine/error flush decisions."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from fex_resume_patches import _function


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    path = args.source / 'wine-nx-probe/source/runtime.c'
    runtime = path.read_text()
    log_header = (ROOT / 'src/runtime/fex_warm_log.h').read_text()
    metric_header = (ROOT / 'src/runtime/fex_warm_runtime.h').read_text()
    if log_header not in runtime or metric_header not in runtime:
        raise RuntimeError('Generated source mismatch')
    policy = _function(runtime, 'fex_log_should_flush')
    harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <pthread.h>
#include <stdarg.h>
static uint64_t ticks;
static uint64_t armGetSystemTick(void) { return __atomic_add_fetch(&ticks, 1000, __ATOMIC_RELAXED); }
static uint64_t armTicksToNs(uint64_t t) { return t; }
static unsigned lines;
static void log_line(const char *fmt, ...) { (void)fmt; ++lines; }
struct disk_cache;
void *__real_disk_cache_get(struct disk_cache *cache, const unsigned char *key, size_t *size) {
    assert(cache == (void *)0x1234 && key[1] == 99 && size);
    *size = key[0] ? 4321 : 0;
    return key[0] ? (void *)0x5678 : NULL;
}
'''
    harness += (ROOT / 'src/runtime/fex_frame_metrics.h').read_text()
    harness += log_header + '\nstatic __thread int fex_log_metrics_batch;\n' + policy + metric_header
    harness += r'''
static void *worker(void *arg) {
    (void)arg;
    const unsigned char key[2] = {1,99};
    for(unsigned i=0;i<2000;++i) {
        size_t size=0;
        assert(__wrap_disk_cache_get((void *)0x1234,key,&size)==(void *)0x5678 && size==4321);
        assert(!fex_log_should_flush("[FEX3-SMC2] blocks=100",1,0));
    }
    return NULL;
}
int main(void) {
    assert(!fex_log_should_flush("[FEX2] thread ready\n",1,0));
    assert(!fex_log_should_flush("[FEX-JIT] slot=1 size=4096",1,0));
    assert(fex_log_should_flush("[FEX-JIT] allocation failed",1,0));
    assert(fex_log_should_flush("[FEX2] thread ready failed",1,0));
    assert(fex_log_should_flush("[FEX3-FAULT] STOP",1,0));
    assert(fex_log_should_flush("[FEX3] unknown",1,0));
    assert(fex_log_should_flush("[EXC] fault",1,1));
    assert(fex_log_should_flush("[FEX3-SMC2] blocks=1",1,1));
    assert(fex_log_should_flush("[FEX3-SMC2] blocks=1",0,0));
    fex_log_metrics_batch=1;
    assert(!fex_log_should_flush("[FEX3-WARM] stats",1,0));
    assert(fex_log_should_flush("[EXIT] stop",1,1));
    fex_log_metrics_batch=0;
    pthread_t threads[8];
    for(unsigned i=0;i<8;++i) assert(!pthread_create(&threads[i],NULL,worker,NULL));
    for(unsigned i=0;i<8;++i) assert(!pthread_join(threads[i],NULL));
    const unsigned char key[2] = {0,99}; size_t size=77;
    assert(!__wrap_disk_cache_get((void *)0x1234,key,&size) && size==0);
    assert(fex_warm_hits==16000 && fex_warm_misses==1 && fex_warm_deferred==16002);
    uint64_t count=0;
    for(unsigned i=0;i<9;++i) count+=fex_warm_stats[2].bins[i];
    assert(count==16001);
    ticks=60000000;
    wine_nx_fex_compile_note(0,0,-4);
    wine_nx_fex_compile_note(1,ticks,0);
    assert(fex_warm_stats[0].bins[5]==1 && fex_warm_errors[0]==1);
    assert(fex_warm_stats[1].bins[0]==1 && fex_warm_errors[1]==0);
    wine_nx_fex_compile_note(4,0,-4);
    fex_warm_report(); fex_warm_report();
    assert(lines==8);
    puts("PASS routine/error flush policy; cache pointer/size passthrough; 16001 concurrent samples; pipeline error and slow-call metrics");
}
'''
    with tempfile.TemporaryDirectory(prefix='fex-warm-') as directory:
        source, binary = Path(directory)/'warm.c', Path(directory)/'warm'
        source.write_text(harness)
        subprocess.run(['clang','-std=c11','-O1','-g','-pthread', '-fsanitize=address,undefined',
                        '-fno-sanitize-recover=all',str(source),'-o',str(binary)],check=True)
        result = subprocess.run([str(binary)],check=True,capture_output=True,text=True,timeout=30)
    report = {'passed': True, 'hardware_tested': False, 'output': result.stdout,
              'runtime_source_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(result.stdout,end='')


if __name__ == '__main__':
    main()
