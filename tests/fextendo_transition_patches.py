"""Verify trace wrappers preserve all native Vulkan call arguments and results."""
import argparse,hashlib,json,re
from pathlib import Path
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('frozen',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();name='dlls/winevulkan/vulkan_thunks.c'
    data=(a.source/name).read_text();original=(a.frozen/name).read_text()
    stripped=data.replace('\nextern unsigned wine_nx_transition_begin(unsigned,uint64_t);\nextern void wine_nx_transition_end(unsigned,int);','')
    pattern=r'    \{ unsigned fx_token=wine_nx_transition_begin\([^\n]*\);\n(    params->result = [^\n]*;)\n    wine_nx_transition_end\(fx_token,params->result\); \}'
    stripped,n=re.subn(pattern,lambda m:m[1],stripped)
    assert n==34,n
    assert stripped==original,'A Vulkan statement changed beyond the observer wrapper'
    process=(a.source/'dlls/ntdll/unix/process.c').read_text()
    assert re.search(r'wine_nx_transition_event\(1,[^\n]+\n\s*horizon_registry_flush\(\)',process)
    h=(a.source/'dlls/ntdll/unix/horizon.c').read_text()
    assert h.count('wine_nx_transition_event(2,')==h.count('wine_nx_transition_event(4,')==1
    assert h.count('wine_nx_transition_event(6,')==1
    runtime=(a.source/'wine-nx-probe/source/runtime.c').read_text()
    crash='#define FX_CRASH_LOG 1' in runtime
    if crash:
        # The callback is only in the existing terminal status branch, after
        # both Wine virtual-memory recovery and guest exception dispatch.
        fatal=h.index('        wine_nx_crash_exception(ctx,(unsigned)status);')
        branch=h.rfind('    if (status)\n    {',0,fatal)
        assert 0<branch<fatal<h.index('"[EXC] desc=',fatal)
        assert h.index('pes13_fex_dispatch_exception(&rec, &context)')<branch
        assert process.index('wine_nx_crash_exit((unsigned)exit_code)')<process.index('horizon_registry_flush();',process.index('wine_nx_crash_exit((unsigned)exit_code)'))
        assert runtime.index('mkdir( RUNTIME_DIR, 0777 );')<runtime.index('fx_crash_bootstrap();')<runtime.index('pthread_create(&maintenance')
        assert 'fx_crash_init(__start__);' not in runtime
        assert 'fx_crash_settings(fx_ui_view.selected,fx_ui_view.renderer);' in runtime
        assert 'fx_crash_failure_line(msg);\n    wine_nx_transition_failure_line(msg);' in runtime
        cmake=(a.source/'wine-nx-probe/CMakeLists.txt').read_text()
        for wrapper in ('abort','diagAbortWithResult','svcBreak'):assert '-Wl,--wrap='+wrapper in cmake
    live='#define FX_LIVE_TRACE 1' in runtime
    if live:
        profile='wine-nx-probe/source/thread_profile.c'
        def normalize(d):return re.sub(r'#include "[^"\n]+/(src/runtime/[^"\n]+)"',r'#include "\1"',d)
        assert normalize((a.source/profile).read_text())==normalize((a.frozen/profile).read_text())+'\n#include "fextendo_live_threads.h"\n'
    loader=(a.source/'dlls/ntdll/loader.c').read_text()
    assert loader.count('wine_nx_transition_fex_image((ULONG_PTR)loaded[3]->ldr.DllBase,loaded[3]->ldr.SizeOfImage)')==1
    alloc=(Path(__file__).resolve().parents[1]/'src/runtime/fextendo_transition_alloc.h').read_text()
    assert 'int saved=errno;' in alloc and 'errno=saved;' in alloc
    r={'passed':True,'hardware_tested':False,'wrapped_native_calls':n,'direct_crash_hooks':crash,'live_thread_observer':live,
       'checks':['Removing observer wrappers reproduces frozen Vulkan source byte-for-byte after newline normalization',
                 'Exit event occurs before registry flush; native exception and section failures each have one hook'],
       'vulkan_source_sha256':hashlib.sha256((a.source/name).read_bytes()).hexdigest()}
    a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
