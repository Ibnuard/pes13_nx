"""Debug-only non-suspending progress evidence for a Kitserver menu stall."""
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def apply(source,feature):
    changed=set()
    def one(data,old,new):
        assert data.count(old)==1,(old[:110],data.count(old))
        return data.replace(old,new)
    def edit(name,fn):
        p=source/name;before=p.read_text();after=fn(before)
        assert after!=before,name
        p.write_text(after);changed.add(name)
    for n in ('fextendo_wait_probe.h','fextendo_wait_threads.h'):
        (feature/n).write_bytes((ROOT/'src/runtime'/n).read_bytes())
    decl='extern uint64_t wine_nx_wait_probe_begin(unsigned,unsigned,uint64_t,uint64_t);\nextern void wine_nx_wait_probe_end(uint64_t,unsigned);\n'
    def runtime(data):
        anchor='static void *log_flusher( void *arg )\n'
        data=one(data,anchor,'#include "fextendo_wait_probe.h"\n'+anchor)
        data=one(data,'        if(ticks%5==0)fx_debug_file_tick();',
            '        if(ticks%25==0)fx_wait_probe_tick();\n        if(ticks%5==0)fx_debug_file_tick();')
        data=one(data,'[FEX3-HANG] v2 capture after 3s no presents; includes idle workers, max 3 captures',
            '[WAIT-PROBE] kit15 v2; Debug launch only, 5s progress, no thread suspension')
        return data
    edit('wine-nx-probe/source/runtime.c',runtime)
    edit('wine-nx-probe/source/thread_profile.c',lambda d:d+'\n#include "fextendo_wait_threads.h"\n')
    def syscall(data):
        anchor='NTSTATUS wine_nx_do_syscall( ULONG_PTR *stack_args,'
        data=one(data,anchor,decl+anchor)
        start=data.index(anchor);end=data.index('\n}\n',start)+3
        block=data[start:end]
        block=one(block,'    NTSTATUS result;','    NTSTATUS result;\n    uint64_t fx_wait_token = 0;')
        # Non-returning context/exception syscalls can unwind over this frame.
        anchor='    if (arg_bytes <= 64)\n'
        block=one(block,anchor,'''    if ((void *)handler != (void *)NtContinue && (void *)handler != (void *)NtRaiseException &&
        (void *)handler != (void *)NtCallbackReturn && (void *)handler != (void *)NtTerminateThread &&
        (void *)handler != (void *)NtTerminateProcess && (void *)handler != (void *)NtReadVirtualMemory)
        fx_wait_token = wine_nx_wait_probe_begin(0, syscall_id, x0, x1);

'''+anchor)
        block=one(block,'    return result;','    wine_nx_wait_probe_end(fx_wait_token, result);\n    return result;')
        return data[:start]+block+data[end:]
    edit('dlls/ntdll/unix/signal_arm64.c',syscall)
    def server(data):
        anchor='unsigned int server_call_unlocked( void *req_ptr )\n'
        data=one(data,anchor,'#ifdef __SWITCH__\n'+decl+'#endif\n'+anchor)
        data=one(data,'    u64 start = armGetSystemTick();',
            '    u64 start = armGetSystemTick();\n    uint64_t fx_wait_token = wine_nx_wait_probe_begin(1, code, 0, 0);')
        start=data.index('unsigned int server_call_unlocked(');end=data.index('\n}\n',start)+3
        block=data[start:end]
        block=one(block,'    return ret;','''#ifdef __SWITCH__
    wine_nx_wait_probe_end(fx_wait_token, ret);
#endif
    return ret;''')
        return data[:start]+block+data[end:]
    edit('dlls/ntdll/unix/server.c',server)
    def vulkan(data):
        data=one(data,'#include "vulkan_private.h"','#include "vulkan_private.h"\n'+decl)
        stages={'AcquireNextImageKHR':0,'AcquireNextImage2KHR':0,'QueuePresentKHR':1,
            'QueueSubmit':2,'QueueSubmit2':2,'QueueSubmit2KHR':2,'WaitForFences':3,
            'WaitSemaphores':4,'WaitSemaphoresKHR':4,'CreateGraphicsPipelines':5,
            'CreateComputePipelines':6,'AllocateMemory':7,'CreateImage':8,'CreateBuffer':9,
            'CreateShaderModule':10,'DeviceWaitIdle':11,'QueueWaitIdle':12}
        for name,stage in stages.items():
            pattern=r'^    params->result = [^\n]*->p_vk'+name+r'\([^\n]*;$'
            def replace(m):
                return ('    { uint64_t fx_wait_token=wine_nx_wait_probe_begin(2,'+str(stage)+',0,0);\n'
                        +m[0]+'\n    wine_nx_wait_probe_end(fx_wait_token,params->result); }')
            data,n=re.subn(pattern,replace,data,flags=re.M);assert n==2,(name,n)
        return data
    edit('dlls/winevulkan/vulkan_thunks.c',vulkan)
    return changed
