"""Compile actual routing code and check unchanged server wait semantics."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,tempfile
p=Path(__file__).resolve().parents[1];sys.path.insert(0,str(p/'tools'))
from perf27_patches import patch_horizon,patch_vulkan,patch_thunks,function_span
root=Path(os.environ.get('PES_BUILD_ROOT','/home/blekjek/pes13-build'))
source=root/'runtime-perf11-source'
original=(source/'dlls/ntdll/unix/horizon.c').read_text()
patched=patch_horizon(original,p)
# The optimization routes notifications only, never substitutes results or
# changes acquisition/consumption, timeout arithmetic or poll intervals.
for name in ('horizon_server_wait_object_locked','horizon_server_select_wait',
             'horizon_server_select_signal_and_wait','horizon_server_select_status',
             'horizon_server_handle_init_thread','horizon_server_end_thread_locked'):
    a,b=function_span(original,name);c,d=function_span(patched,name)
    assert original[a:b]==patched[c:d],name
assert patched.count('pes27_signal_object_locked(object);')==6
assert 'horizon_server_sleep_locked( HORIZON_SERVER_WAIT_SLICE );' in patched
v=(source/'dlls/win32u/vulkan.c').read_text()
assert 'PES27_PRESENT' in patch_vulkan(v,p)
t=(source/'dlls/winevulkan/vulkan_thunks.c').read_text()
assert patch_thunks(t,p).count('PES27_TIME(')==8
with tempfile.TemporaryDirectory(prefix='perf27-wait-',dir=root) as tmp:
    binary=Path(tmp)/'wait'
    subprocess.run(['cc','-O2','-g','-std=gnu11','-Wall','-Wextra','-Werror','-pthread',
        '-fsanitize=address,undefined',str(p/'tests/perf27_wait.c'),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True,timeout=60)
    # Compile the real Horizon identity resolver with fixture handles. Broad
    # fallback for polling objects must survive adding new object types.
    h=(p/'src/runtime/pes13_perf27_horizon.h').read_text()
    a,b=function_span(h,'pes27_resolve')
    fixture=Path(tmp)/'resolver.c'
    fixture.write_text('''#include <assert.h>
#include <stddef.h>
enum { HORIZON_SERVER_OBJECT_EVENT=1, HORIZON_SERVER_OBJECT_MUTEX,
 HORIZON_SERVER_OBJECT_SEMAPHORE, HORIZON_SERVER_OBJECT_THREAD };
#define HORIZON_CURRENT_THREAD_HANDLE 0xfffffffeu
struct horizon_server_object { int type; } objects[12];
struct horizon_server_handle_entry { struct horizon_server_object *object; } entries[12];
static struct horizon_server_handle_entry *horizon_server_find_handle_locked(unsigned int h)
{ return h<12 ? &entries[h] : NULL; }
'''+h[a:b]+'''
int main(void) {
 for(unsigned i=0;i<12;++i) { objects[i].type=i;entries[i].object=&objects[i]; }
 for(unsigned i=0;i<12;++i) assert(pes27_resolve(i,NULL)==(i>=1 && i<=4 ? &objects[i] : NULL));
 assert(!pes27_resolve(99,NULL));
 assert(pes27_resolve(HORIZON_CURRENT_THREAD_HANDLE,&objects[4])==&objects[4]);
 entries[2].object=&objects[1];assert(pes27_resolve(1,NULL)==pes27_resolve(2,NULL));
 return 0;
}
''')
    subprocess.run(['cc','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                    str(fixture),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
    subprocess.run(['cc','-O2','-pthread','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
        str(source/'wine-nx-probe/tests/horizon_threads.c'),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True,timeout=60)
w=p/'local/perf27';w.mkdir(exist_ok=True,parents=True)
report={'asan_ubsan':'PASS','real_resolver_and_upstream_thread_tests':'PASS',
    'concurrent_handoffs':16000,'synthetic_candidates':2000000,
    'synthetic_notifications':100000,'game_fps_benchmark':False,'server_wait_result_code_unchanged':True,
    'source_sha256':{str(f.relative_to(p)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [
        p/'src/runtime/pes13_perf27_wait.h',p/'src/runtime/pes13_perf27_horizon.h',
        p/'src/runtime/pes13_perf27_metrics.h',p/'src/runtime/pes13_perf27_runtime.h',
        p/'tools/perf27_patches.py',p/'tests/perf27_wait.c',p/'tests/perf27_wait.py']}}
(w/'wait-tests.json').write_text(json.dumps(report,indent=2)+'\n')
