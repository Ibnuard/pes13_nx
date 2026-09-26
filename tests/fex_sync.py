"""Check the actual FEX router, unchanged wait semantics and delay diagnostics."""
from pathlib import Path
import argparse, hashlib, json, subprocess, sys

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--build-root',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args(); root=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(root/'tools'))
    from perf27_patches import function_span
    work=a.build_root/'fex-experiment/wine3'
    source=work/'native-source'; original=work/'native-source-originals'
    data=(source/'dlls/ntdll/unix/horizon.c').read_text()
    old=(original/'dlls/ntdll/unix/horizon.c').read_text()
    def body(text,name):
        b,e=function_span(text,name); return text[b:e]
    unchanged=('horizon_server_sleep_locked','horizon_server_wait_object_locked',
               'horizon_server_select_wait','horizon_server_select_status',
               'horizon_server_select_signal_and_wait','horizon_server_handle_resume_thread',
               'horizon_server_end_thread_locked','horizon_server_select_polls_locked')
    for name in unchanged: assert body(data,name)==body(old,name),name
    assert (root/'src/runtime/fex_self_suspend.h').read_text() in data
    assert data.count('fex_sync_signal_object_locked(object);')==6
    assert data.count('fex_sync_select_sleep_locked( timeout, &interest );')==1
    assert 'if (wine_nx_fex_targeted_wake)\n        pes27_decode(' in data
    runtime=(source/'wine-nx-probe/source/runtime.c').read_text()
    assert 'int wine_nx_fex_targeted_wake = 0;' in runtime
    assert 'wine_nx_config_file_bool(RUNTIME_DIR "/fex-targeted-wake.txt", 0)' in runtime
    sync=(source/'dlls/ntdll/unix/sync.c').read_text()
    sync_old=(original/'dlls/ntdll/unix/sync.c').read_text()
    assert body(sync,'fex_delay_impl').replace('static NTSTATUS fex_delay_impl(',
        'NTSTATUS WINAPI NtDelayExecution(',1)==body(sync_old,'NtDelayExecution')
    for name in ('NtYieldExecution','NtQuerySystemTime','NtQueryPerformanceCounter'):
        assert body(sync,name)==body(sync_old,name),name
    fixture=a.build_root/'fex-experiment/sync-test'; fixture.mkdir(exist_ok=True)
    adapter=(root/'src/runtime/fex_sync_horizon.h').read_text()+'\n'+body(data,'horizon_server_sleep_locked')
    # Linux pthread types lack libnx's nested cond/normal members. Only adapt
    # these field addresses; keep all routing/locking/control flow intact.
    for name in ('private_cond','horizon_server_objects_cond'):
        adapter=adapter.replace('&'+name+'.cond','&'+name)
    adapter=adapter.replace('&horizon_server_objects_mutex.normal','&horizon_server_objects_mutex')
    (fixture/'fex_sync_adapter.inc').write_text(adapter)
    # Invoke the actual public wrapper with modeled native dependencies,
    # including a native helper thread that has no Wine TEB.
    (fixture/'delay-wrapper.c').write_text('''#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#define WINAPI
typedef int NTSTATUS;
typedef int BOOLEAN;
typedef uintptr_t ULONG_PTR;
typedef struct { int64_t QuadPart; } LARGE_INTEGER;
typedef struct { struct { void *UniqueThread; } ClientId; } TEB;
static TEB thread = {{(void*)4}}, *current;
static int calls, notes, expect_alert, result;
static const LARGE_INTEGER *expect_timeout;
static uint64_t wine_nx_fex_frame_tick(void) { return 123; }
static TEB *NtCurrentTeb(void) { return current; }
static NTSTATUS fex_delay_impl(BOOLEAN alert, const LARGE_INTEGER *timeout)
{ assert(alert==expect_alert && timeout==expect_timeout); ++calls; return result; }
void wine_nx_fex_delay_note(unsigned tid,int alert,int has,int64_t timeout,uint64_t begin,int status)
{ assert(tid==4 && alert==expect_alert && has==!!expect_timeout &&
    timeout==(has?expect_timeout->QuadPart:0) && begin==123 && status==result); ++notes; }
'''+body(sync,'NtDelayExecution')+'''
int main(void) {
 LARGE_INTEGER values[]={{0},{-50000},{100000},{INT64_MIN}};
 for(int t=0;t<2;++t) for(int al=0;al<2;++al) for(int n=0;n<5;++n) {
  current=t?&thread:NULL; expect_alert=al; expect_timeout=n<4?&values[n]:NULL;
  result=(al||n==4)?-1:0; int before=notes, prev=calls;
  assert(NtDelayExecution(al,expect_timeout)==result && calls==prev+1 && notes==before+t);
 }
 return 0;
}
''')
    outputs=[]
    for test in ('perf27_wait.c','fex_sync_native.c','fex_delay_native.c','delay-wrapper.c'):
        binary=fixture/test.removesuffix('.c')
        test_source=fixture/test if test=='delay-wrapper.c' else root/'tests'/test
        subprocess.run(['cc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror',
            '-fsanitize=address,undefined','-pthread','-I'+str(fixture),'-I'+str(root/'src/runtime'),
            str(test_source),'-o',str(binary)],check=True)
        result=subprocess.run([str(binary)],text=True,capture_output=True,timeout=45)
        if result.returncode: print(result.stdout,result.stderr,file=sys.stderr)
        result.check_returncode()
        outputs.append(result.stdout.strip())
    names=('tools/fex_sync_patches.py','src/runtime/fex_sync_horizon.h','src/runtime/fex_sync_runtime.h',
           'src/runtime/pes13_perf27_wait.h','tests/perf27_wait.c','tests/fex_sync_native.c',
           'tests/fex_delay_native.c','tests/fex_sync.py')
    sha=lambda b:hashlib.sha256(b).hexdigest()
    report={'passed':True,'hardware_tested':False,'sanitizers':['address','undefined'],
            'unchanged_functions':unchanged,'guest_clocks_and_delay_policy_unchanged':True,
            'output':outputs,'source_sha256':{p:sha((root/p).read_bytes()) for p in names},
            'patched_source_sha256':{p:sha((source/p).read_bytes()) for p in
                ('dlls/ntdll/unix/horizon.c','dlls/ntdll/unix/sync.c','wine-nx-probe/source/runtime.c')}}
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__': main()
