"""Narrow, opt-in HIGH freeze evidence over the verified production source."""
import re

def apply(source,feature,crash_log=False,live_freeze=False):
    changed={}
    def edit(name,fn):
        p=source/name;before=p.read_text();after=fn(before)
        assert before!=after,name
        p.write_text(after);changed[name]=after
    def one(data,old,new):
        assert data.count(old)==1,old[:120]
        return data.replace(old,new)
    runtime='wine-nx-probe/source/runtime.c'
    def runtime_patch(data):
        data=one(data,'#include <switch.h>','#include <switch.h>\n#define FX_TRANSITION_TRACE 1\n#include "fextendo_transition_trace.h"')
        if live_freeze:
            data=one(data,'#define FX_TRANSITION_TRACE 1','#define FX_TRANSITION_TRACE 1\n#define FX_LIVE_TRACE 1\n#include "fextendo_live_trace.h"')
        data=one(data,'#include <malloc.h>','#include <malloc.h>\n#include "fextendo_transition_alloc.h"')
        # The null sink is archived production source. Inline a local instrumented
        # copy, rather than editing the verified baseline archive.
        match=re.search(r'#include "([^"]*/src/runtime/fextendo_silent_io.h)"',data)
        assert match
        from pathlib import Path
        sink=Path(match[1]).read_text()
        old='    (void)r; (void)fd; (void)data; return (ssize_t)size;'
        sink=one(sink,old,'    (void)r; (void)fd; wine_nx_transition_text(data,size); return (ssize_t)size;')
        data=data[:match.start()]+sink+data[match.end():]
        data=one(data,'    (void)stream; (void)data; (void)size;',
                 '    (void)stream; wine_nx_transition_text(data,size);')
        data=one(data,'void wine_nx_runtime_trace( const char *msg )\n{\n    (void)msg;\n}',
                 'void wine_nx_runtime_trace( const char *msg )\n{\n    wine_nx_transition_failure_line(msg);\n}')
        if crash_log:
            data=one(data,'#define RUNTIME_DIR WINE_ROOT',
                '#define RUNTIME_DIR WINE_ROOT\n#define FX_CRASH_LOG 1\n#include "fextendo_crash.h"')
            data=one(data,'    wine_nx_transition_failure_line(msg);',
                '    fx_crash_failure_line(msg);\n    wine_nx_transition_failure_line(msg);')
            anchor='    mkdir( RUNTIME_DIR, 0777 );'
            data=one(data,anchor,anchor+'\n    fx_crash_bootstrap();')
            anchor='    else if (!fx_launcher_start()) return 0;'
            data=one(data,anchor,anchor+'\n    fx_crash_settings(fx_ui_view.selected,fx_ui_view.renderer);')
        return data
    edit(runtime,runtime_patch)
    if live_freeze:
        edit('wine-nx-probe/source/thread_profile.c',lambda d:d+'\n#include "fextendo_live_threads.h"\n')
    declaration='extern void wine_nx_transition_event(unsigned,unsigned,unsigned long long,unsigned long long);\n'
    def process(data):
        anchor='        horizon_registry_flush();\n        if (&wine_nx_runtime_trace)'
        extra=('        extern void wine_nx_crash_exit(unsigned);\n'
               '        wine_nx_crash_exit((unsigned)exit_code);\n') if crash_log else ''
        return one(data,anchor,extra+'        '+declaration+
            '        wine_nx_transition_event(1,(unsigned)exit_code,0,0);\n'+anchor)
    edit('dlls/ntdll/unix/process.c',process)
    def loader(data):
        anchor='        if (!status) status = pes13_fex_install_module(loaded[3]->ldr.DllBase);'
        extra=('        extern void wine_nx_crash_fex_image(unsigned long long,unsigned long long);\n'
               '        wine_nx_crash_fex_image((ULONG_PTR)loaded[3]->ldr.DllBase,loaded[3]->ldr.SizeOfImage);\n') if crash_log else ''
        return one(data,anchor,extra+'        extern void wine_nx_transition_fex_image(unsigned long long,unsigned long long);\n'
            '        wine_nx_transition_fex_image((ULONG_PTR)loaded[3]->ldr.DllBase,loaded[3]->ldr.SizeOfImage);\n'+anchor)
    edit('dlls/ntdll/loader.c',loader)
    def horizon(data):
        if crash_log:
            anchor='        /* Handled page faults are ordinary VM activity and must never hit the\n'
            data=one(data,anchor,'        extern void wine_nx_crash_exception(const void *,unsigned);\n'
                     '        wine_nx_crash_exception(ctx,(unsigned)status);\n'+anchor)
        anchor='        snprintf( buf, sizeof(buf), "[EXC] unhandled status=0x%08x; parking thread", (unsigned)status );'
        data=one(data,anchor,'        '+declaration+
            '        wine_nx_transition_event(2,(unsigned)status,ctx->pc.x,ctx->far.x);\n'
            '        wine_nx_transition_event(6,(unsigned)ctx->esr,ctx->lr.x,ctx->sp.x);\n'+anchor)
        anchor='    if (++section_failures > 16) return;'
        return one(data,anchor,'    '+declaration+
            '    wine_nx_transition_event(4,(unsigned)error,size,(unsigned long long)addr);\n'+anchor)
    edit('dlls/ntdll/unix/horizon.c',horizon)
    counts={}
    def vulkan(data):
        data=one(data,'#include "vulkan_private.h"','#include "vulkan_private.h"\n'
            'extern unsigned wine_nx_transition_begin(unsigned,uint64_t);\n'
            'extern void wine_nx_transition_end(unsigned,int);')
        stages={'AcquireNextImageKHR':(0,'params->timeout'),'AcquireNextImage2KHR':(0,'0'),
            'QueuePresentKHR':(1,'0'),'QueueSubmit':(2,'params->submitCount'),'QueueSubmit2':(2,'params->submitCount'),
            'QueueSubmit2KHR':(2,'params->submitCount'),'WaitForFences':(3,'params->timeout'),
            'WaitSemaphores':(4,'params->timeout'),'WaitSemaphoresKHR':(4,'params->timeout'),
            'CreateGraphicsPipelines':(5,'params->createInfoCount'),'CreateComputePipelines':(6,'params->createInfoCount'),
            'AllocateMemory':(7,'pAllocateInfo_host.allocationSize'),'CreateImage':(8,'0'),
            'CreateBuffer':(9,'pCreateInfo_host.size'),'CreateShaderModule':(10,'0'),
            'DeviceWaitIdle':(11,'0'),'QueueWaitIdle':(12,'0')}
        for name,(stage,detail) in stages.items():
            pattern=r'^    params->result = [^\n]*->p_vk'+name+r'\([^\n]*;$'
            def replace(m):
                return '    { unsigned fx_token=wine_nx_transition_begin('+str(stage)+','+detail+');\n'+m[0]+'\n    wine_nx_transition_end(fx_token,params->result); }'
            data,n=re.subn(pattern,replace,data,flags=re.M);assert n==2,(name,n);counts[name]=n
        return data
    edit('dlls/winevulkan/vulkan_thunks.c',vulkan)
    edit('wine-nx-probe/CMakeLists.txt',lambda d:d+'\ntarget_link_options(wine-nx-runtime PRIVATE -Wl,--wrap=malloc -Wl,--wrap=calloc -Wl,--wrap=realloc -Wl,--wrap=memalign -Wl,--wrap=aligned_alloc)\n')
    if crash_log:
        edit('wine-nx-probe/CMakeLists.txt',lambda d:d+'\ntarget_link_options(wine-nx-runtime PRIVATE -Wl,--wrap=abort -Wl,--wrap=diagAbortWithResult -Wl,--wrap=svcBreak)\n')
    return sorted(changed),counts
