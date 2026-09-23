"""PERF26 CPU code with targeted Horizon notifications and bounded stage timing."""
from pathlib import Path
import re
import perf26_patches
from perf17_patches import once

adapt_profile = perf26_patches.adapt_profile

def function_span(text, name):
    start = text.index(name + '(') if name+'(' in text else text.index(name+' (')
    start = text.rfind('\n', 0, start) + 1
    brace = text.index('{', start); depth = 1; end = brace+1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}'); end += 1
    return start, end

def patch_horizon(text, project):
    a,b = function_span(text, 'horizon_server_signal_changed_locked')
    c,d = function_span(text, 'horizon_server_sleep_locked')
    assert a<b<c<d
    text = text[:a] + '#include "'+str(project/'src/runtime/pes13_perf27_horizon.h')+'"\n' + text[d:]
    # Only these state changes have one known dependency. Completion ports,
    # thread exit/abandonment, startup gates and other sources retain wake-all.
    for name, count in [('horizon_server_signal_object_locked',3),
                        ('horizon_server_handle_event_op',1),
                        ('horizon_server_handle_release_mutex',1),
                        ('horizon_server_handle_release_semaphore',1)]:
        a,b=function_span(text,name); body=text[a:b]
        assert body.count('horizon_server_signal_changed_locked();')==count
        body=body.replace('horizon_server_signal_changed_locked();','pes27_signal_object_locked(object);')
        text=text[:a]+body+text[b:]
    a,b=function_span(text,'horizon_server_handle_select');body=text[a:b]
    body=once(body,'    int polls;', '    int polls;\n    struct pes27_interest interest;')
    body=once(body,'    polls = horizon_server_select_polls_locked( request, data, data_size );',
        '''    polls = horizon_server_select_polls_locked( request, data, data_size );
    _Static_assert(offsetof(struct horizon_select_wait_op, handles) == 4, "wait wire offset");
    _Static_assert(offsetof(struct horizon_select_signal_and_wait_op, wait) == 4, "signal wait offset");
    _Static_assert(sizeof(struct horizon_select_signal_and_wait_op) == 12, "signal wait size");
    pes27_decode(&interest, data, data_size, request->size, HORIZON_APC_RESULT_SIZE,
        HORIZON_SELECT_WAIT, HORIZON_SELECT_WAIT_ALL, HORIZON_SELECT_SIGNAL_AND_WAIT, connection->thread);''')
    body=once(body,'        horizon_server_sleep_locked( timeout );','        pes27_sleep_locked( timeout, &interest );')
    return text[:a]+body+text[b:]

def timed_calls(text, method, stage, expected):
    pattern=r'(?m)^( +)((?:res|params->result) = (?:[^;\n]*->)?'+method+r'\([\s\S]*?\);)'
    matches=list(re.finditer(pattern,text));assert len(matches)==expected,(method,len(matches))
    return re.sub(pattern,lambda m:m[1]+'PES27_TIME('+stage+', '+m[2][:-1]+');',text)

def patch_vulkan(text, project):
    text='#include "'+str(project/'src/runtime/pes13_perf27_metrics.h')+'"\n'+text
    text=timed_calls(text,'p_vkAcquireNextImageKHR','PES27_ACQUIRE',1)
    text=timed_calls(text,'p_vkAcquireNextImage2KHR','PES27_ACQUIRE',1)
    text=timed_calls(text,'p_vkQueueSubmit','PES27_SUBMIT',1)
    text=timed_calls(text,'p_vkQueueSubmit2','PES27_SUBMIT',1)
    a,b=function_span(text,'win32u_vkQueuePresentKHR');body=text[a:b]
    body=once(body,'    pthread_mutex_lock( &lock );','    PES27_TIME(PES27_PRESENT_LOCK, pthread_mutex_lock( &lock ));')
    body=once(body,'        client_surface_update( surface->client );',
        '        PES27_TIME(PES27_SURFACE_BEFORE, client_surface_update( surface->client ));')
    anchor='    for (uint32_t i = 0; i < present_info->swapchainCount; i++)\n    {\n        struct swapchain *swapchain = swapchain_from_handle( client_swapchains[i] );\n        VkResult'
    body=once(body,anchor,'    unsigned long long pes27_after = wine_nx_perf8_tick();\n'+anchor)
    body=once(body,'    nx_vk_note_present( client_swapchains, present_info->swapchainCount, res );',
        '    wine_nx_perf27_span(PES27_SURFACE_AFTER, wine_nx_perf8_tick() - pes27_after);\n    nx_vk_note_present( client_swapchains, present_info->swapchainCount, res );')
    body=once(body,'win32u_vkQueuePresentKHR(', 'pes27_present_impl(')
    wrapper='''
static VkResult win32u_vkQueuePresentKHR(VkQueue queue, const VkPresentInfoKHR *info)
{
    VkResult res;
    PES27_TIME(PES27_PRESENT, res = pes27_present_impl(queue, info));
    return res;
}
'''
    return text[:a]+body+wrapper+text[b:]

def patch_thunks(text,project):
    text='#include "'+str(project/'src/runtime/pes13_perf27_metrics.h')+'"\n'+text
    for method,stage in [('p_vkWaitForFences','PES27_FENCE'),('p_vkWaitSemaphores','PES27_SEMAPHORE'),
                         ('p_vkQueueWaitIdle','PES27_IDLE'),('p_vkDeviceWaitIdle','PES27_IDLE')]:
        text=timed_calls(text,method,stage,2)
    return text

def adapt_recipe(text):
    text=perf26_patches.adapt_recipe(text)
    text=once(text,'    horizon_source.write_text(horizon_text)',
        '    from perf27_patches import patch_horizon, patch_thunks\n'
        '    horizon_text = patch_horizon(horizon_text, project)\n'
        '    (project/"local/perf27/horizon.c").write_text(horizon_text)\n'
        '    horizon_source.write_text(horizon_text)\n'
        '    thunks_source.write_text(patch_thunks(originals[thunks_source].decode(), project))')
    text=once(text,'    vulkan_source.write_text(vulkan_text)',
        '    from perf27_patches import patch_vulkan\n'
        '    vulkan_text = patch_vulkan(vulkan_text, project)\n'
        '    (project/"local/perf27/vulkan.c").write_text(vulkan_text)\n'
        '    vulkan_source.write_text(vulkan_text)')
    text=once(text,'originals = {','thunks_source = wine_source / "dlls/winevulkan/vulkan_thunks.c"\noriginals = {')
    return once(text,'vulkan_source, runtime_source, horizon_source,','vulkan_source, runtime_source, horizon_source, thunks_source,')

def adapt(cmake,dynarec,runtime,project):
    path=project/'tools/perf26_patches.py';ns={'__file__':str(path),'__name__':'perf27_base'}
    exec(compile(path.read_text().replace('local/perf26','local/perf27'),str(path),'exec'),ns)
    cmake,dynarec,runtime=ns['adapt'](cmake,dynarec,runtime,project)
    runtime=once(runtime,'static void log_line(const char *fmt, ...);',
        'static void log_line(const char *fmt, ...);\n#include "'+str(project/'src/runtime/pes13_perf27_runtime.h')+'"')
    runtime=once(runtime,'    wine_nx_thread_report();','    pes27_report();\n    wine_nx_thread_report();')
    return cmake,dynarec,runtime
