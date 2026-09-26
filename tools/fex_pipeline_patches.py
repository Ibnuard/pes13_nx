"""Observe pre-present native stages without changing their return/wait semantics."""
import re


def apply(read, replace, project):
    name = 'wine-nx-probe/source/runtime.c'
    anchor = 'static void *log_flusher( void *arg )'
    replace(name, anchor, (project / 'src/runtime/fex_pipeline_runtime.h').read_text() + '\n' + anchor)
    replace(name, '        if (ticks % 50 == 0) fex_frame_report();',
            '        if (ticks % 50 == 0) { fex_frame_report(); fex_pipeline_report(); }')

    name = 'dlls/win32u/vulkan.c'
    # Declarations must precede image-acquisition functions as well as present.
    anchor = 'static VkResult win32u_vkAcquireNextImage2KHR('
    replace(name, anchor, 'extern uint64_t wine_nx_fex_frame_tick(void);\n'
            'extern void wine_nx_fex_pipeline_note(unsigned, uint64_t, int);\n\n' + anchor)
    calls = (
        (0, '    res = device->p_vkAcquireNextImage2KHR( device->host.device, &acquire_info_host, image_index );'),
        (0, '    res = device->p_vkAcquireNextImageKHR( device->host.device, swapchain->obj.host.swapchain, timeout,\n'
            '                                              semaphore ? semaphore->host.semaphore : 0, fence ? fence->host.fence : 0,\n'
            '                                              image_index );'),
        (1, '    res = device->p_vkQueueSubmit( queue->host.queue, count, submits, fence ? fence->host.fence : 0 );'),
        (1, '    res = p_vkQueueSubmit2( queue->host.queue, count, submits, fence ? fence->host.fence : 0 );'),
    )
    for stage, call in calls:
        replace(name, call, '    {\n        uint64_t fex_stage_begin = wine_nx_fex_frame_tick();\n' +
                call + '\n        wine_nx_fex_pipeline_note(' + str(stage) + ', fex_stage_begin, res);\n    }')

    # Native Wine-Vulkan conversion thunks, both 32/64-bit and KHR aliases.
    # The exact driver call/timeout/result remains intact, including failures.
    name = 'dlls/winevulkan/vulkan_thunks.c'
    anchor = '#ifdef _WIN64\nstatic NTSTATUS thunk64_vkWaitForFences(void *args)'
    # The Horizon target can compile only the thunk32 dispatch table despite
    # using native ARM64 pointers. Keep the 64-bit counter declaration outside
    # the _WIN64 guard: an implicit int return would truncate system ticks.
    replace(name, anchor, 'extern uint64_t wine_nx_fex_frame_tick(void);\n'
            'extern void wine_nx_fex_pipeline_note(unsigned, uint64_t, int);\n\n' + anchor)
    data = read(name)
    calls = re.findall(r'^    params->result = .*?->p_vkWait(?:ForFences|Semaphores(?:KHR)?)\([^\n]+;$', data, re.M)
    assert len(calls) == 6
    for call in calls:
        stage = 2 if 'p_vkWaitForFences(' in call else 3
        replace(name, call, '    {\n        uint64_t fex_stage_begin = wine_nx_fex_frame_tick();\n' +
                call + '\n        wine_nx_fex_pipeline_note(' + str(stage) + ', fex_stage_begin, params->result);\n    }')

    name = 'dlls/ntdll/unix/virtual.c'
    replace(name, 'static void usd_update_time(void)',
            'extern void wine_nx_fex_shared_clock_note(uint64_t interrupt_time);\n\nstatic void usd_update_time(void)')
    replace(name, '    __atomic_store_n( &data->TickCountQuad, tick_count, __ATOMIC_RELEASE );',
            '    __atomic_store_n( &data->TickCountQuad, tick_count, __ATOMIC_RELEASE );\n'
            '    wine_nx_fex_shared_clock_note(interrupt_time);')
