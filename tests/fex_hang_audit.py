"""Exercise actual generated hang observer and scaled submit with modeled boundaries."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from fex_resume_patches import _function


def run_cpp(folder, name, text, language='c'):
    source, binary = folder / (name + '.' + language), folder / name
    source.write_text(text)
    subprocess.run(['clang', '-std=c11', '-O1', '-g', '-fsanitize=address,undefined',
                    '-fno-sanitize-recover=all', '-pthread', '-I' + str(ROOT / 'src/fex'),
                    str(source), '-o', str(binary)], check=True)
    return subprocess.run([str(binary)], capture_output=True, text=True, timeout=40)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    profile_path = args.source / 'wine-nx-probe/source/thread_profile.c'
    vulkan_path = args.source / 'dlls/win32u/vulkan.c'
    profile = profile_path.read_text()
    observer = profile[profile.index('/* FEX-only, included at the end'):]
    vulkan = vulkan_path.read_text()
    submit = _function(vulkan, 'nx_submit_scaled')
    # Extract the actual call-site guard from the generated present function.
    guard = re.search(r'^        if \(\(res = nx_submit_scaled[^\n]+$', vulkan, re.M)
    if guard is None or 'scaled present %d read back' in vulkan:
        raise RuntimeError('Incorrect production scaled path')
    runs = {}
    with tempfile.TemporaryDirectory(prefix='fex-hang-tests-') as directory:
        folder = Path(directory)
        header = folder / 'observer.h'
        header.write_text(observer)
        native = (ROOT / 'tests/fex_stall_native.c').read_text()
        native = native.replace('assert(h < 5);', 'assert(h < 32);')
        native = native.replace('#include "../src/runtime/fex_stall_probe.h"',
            'static unsigned refreshes, waiter_reports;\n'
            'static void wine_nx_thread_report(void) { ++refreshes; }\n'
            'void wine_nx_fex_hang_waiters_report(void) { ++waiter_reports; }\n'
            '#include "' + str(header) + '"')
        native = native.replace('#include "../src/runtime/fex_suspend_observe.h"',
                                '#include "' + str(ROOT / 'src/runtime/fex_suspend_observe.h') + '"')
        # New probe captures at 3 seconds, keeping the old independent 10s gate tests.
        native = native.replace('wine_nx_fex_stall_probe(120, 20);', 'wine_nx_fex_stall_probe(120, 17);')
        native = native.replace('wine_nx_fex_stall_probe(120, 25);', 'wine_nx_fex_stall_probe(120, 18);')
        native = native.replace('wine_nx_fex_stall_probe(120, 30);', 'wine_nx_fex_stall_probe(120, 23);')
        native = native.replace('wine_nx_fex_stall_probe(120, 35);', 'wine_nx_fex_stall_probe(120, 28);')
        anchor = '    puts("PASS stall observer:'
        extra = '''    assert(refreshes == 3 && waiter_reports == 3);
    const struct nx_prof_row idle[] = {{1,4,0,'w',0,0},{2,52,0,'w',0,0},{3,56,0,'w',0,0}};
    wine_nx_fex_stall_targets(idle,3);
    assert(fex_stall_targets[1].tid==52 && fex_stall_targets[2].tid==56);
    struct nx_prof_row many[128];
    for(unsigned i=0;i<128;i++) many[i]=(struct nx_prof_row){i+1,i+100,0,'w',0,0};
    wine_nx_fex_stall_targets(many,128);
    assert(fex_stall_targets[63].tid==163);
    wine_nx_fex_stall_remove(64);
    assert(!fex_stall_targets[63].handle);
'''
        native = native.replace(anchor, extra + anchor)
        result = run_cpp(folder, 'observer', native)
        result.check_returncode()
        runs['observer'] = result.stdout

        prefix = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
typedef int VkResult;
typedef uint64_t VkQueue, VkFence;
typedef struct { unsigned commandBufferCount, signalSemaphoreCount; const void *pCommandBuffers,*pSignalSemaphores; } VkSubmitInfo;
#define VK_NULL_HANDLE 0
struct vulkan_device { VkResult (*p_vkQueueSubmit)(VkQueue,unsigned,const VkSubmitInfo*,VkFence); };
struct vulkan_queue { struct vulkan_device *device; struct { VkQueue queue; } host; };
static unsigned calls, metrics, presents; static int outcome;
static const VkSubmitInfo *expected;
uint64_t wine_nx_fex_frame_tick(void) { return 123456; }
void wine_nx_fex_pipeline_note(unsigned stage,uint64_t begin,int result) {
    assert(stage==1 && begin==123456 && result==outcome); ++metrics;
}
static VkResult queue_submit(VkQueue queue,unsigned n,const VkSubmitInfo *info,VkFence fence) {
    assert(queue==42 && n==1 && info==expected && fence==0); ++calls; return outcome;
}
'''
        tail = r'''
    ++presents;
failed:
    return res;
}
int main(void) {
    struct vulkan_device device={queue_submit}; struct vulkan_queue queue={&device,{42}};
    VkSubmitInfo info={2,1,(void*)0x400,(void*)0x800}; expected=&info;
    for(unsigned i=0;i<3601;i++) { outcome=0; assert(present(&queue,&info)==0); }
    assert(calls==3601 && metrics==3601 && presents==3601);
    outcome=-4; assert(present(&queue,&info)==-4);
    assert(calls==3602 && metrics==3602 && presents==3601);
    outcome=-1; assert(present(&queue,&info)==-1);
    assert(calls==3603 && metrics==3603 && presents==3601);
    assert(info.commandBufferCount==2 && info.signalSemaphoreCount==1 && info.pCommandBuffers==(void*)0x400 && info.pSignalSemaphores==(void*)0x800);
    puts("PASS scaled submit: 3601 frames, no readback, original commands/semaphores, errors skip Present");
}
'''
        call = guard.group().replace('&submit_info', 'info')
        harness = prefix + submit + '\nstatic VkResult present(struct vulkan_queue *queue,VkSubmitInfo *info) { int res=0;\n' + call + tail
        result = run_cpp(folder, 'scaled', harness)
        result.check_returncode()
        runs['scaled_submit'] = result.stdout
        mutant = run_cpp(folder, 'scaled_mutant', harness.replace('goto failed;', '(void)res;'))
        if mutant.returncode == 0 or 'Assertion failed' not in mutant.stderr:
            raise RuntimeError('Dropped submit error propagation was not detected')
        waiters = (ROOT / 'src/runtime/fex_hang_waiters.h').read_text()
        waiter_test = r'''
#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
struct horizon_server_object { struct { unsigned tid, suspend, terminated; } thread; };
struct fex_resume_waiter { struct fex_resume_waiter *next; struct horizon_server_object *object; };
static struct fex_resume_waiter *fex_resume_waiters;
static pthread_mutex_t horizon_server_objects_mutex=PTHREAD_MUTEX_INITIALIZER;
static unsigned logs;
void wine_nx_runtime_trace(const char *line) {
    assert(pthread_mutex_trylock(&horizon_server_objects_mutex)==0);
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    assert(strstr(line,"[FEX3-HANG-WAIT")); ++logs;
}
''' + waiters + r'''
int main(void) {
    wine_nx_fex_hang_waiters_report(); assert(logs==1);
    struct horizon_server_object objects[70]; struct fex_resume_waiter nodes[70];
    for(unsigned i=0;i<70;i++) {
        objects[i].thread.tid=4*(i+1); objects[i].thread.suspend=i%4+1;
        objects[i].thread.terminated=0; nodes[i].object=&objects[i];
        nodes[i].next=i<69?&nodes[i+1]:NULL;
    }
    fex_resume_waiters=nodes; wine_nx_fex_hang_waiters_report(); assert(logs==66);
    for(unsigned i=0;i<70;i++) assert(objects[i].thread.suspend==i%4+1);
    puts("PASS waiter snapshot: empty/full capacity, counts preserved, no logging under object mutex");
}
'''
        result = run_cpp(folder, 'waiters', waiter_test)
        result.check_returncode()
        runs['waiters'] = result.stdout
    report = {'passed': True, 'hardware_tested': False,
              'source_sha256': {str(p.relative_to(args.source)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in (profile_path, vulkan_path)},
              'runs': runs, 'lost_error_propagation_mutation_rejected': True,
              'scope': 'Actual generated source slices under ASan/UBSan; kernel/GPU modeled'}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
