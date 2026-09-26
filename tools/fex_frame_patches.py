"""Measure native present stalls without changing guest clocks or wait semantics."""


def apply(read, replace, project):
    name = 'wine-nx-probe/source/runtime.c'
    anchor = 'static void *log_flusher( void *arg )'
    replace(name, anchor,
            (project / 'src/runtime/fex_frame_metrics.h').read_text() + '\n' +
            (project / 'src/runtime/fex_frame_runtime.h').read_text() + '\n' + anchor)
    replace(name, '        if (ticks % 10 == 0) wine_nx_thread_balance();',
            '        if (ticks % 50 == 0) fex_frame_report();\n'
            '        if (ticks % 10 == 0) wine_nx_thread_balance();')
    # Sorted, NUL-separated Wine environment. Explicit path avoids an old
    # unrelated dxvk.conf if a launcher's current-directory rules change.
    replace(name, 'static const char runtime_environment[] =\n',
            'static const char runtime_environment[] =\n'
            '    "DXVK_CONFIG_FILE=C:\\\\PES13\\\\dxvk.conf\\0"\n')

    name = 'dlls/win32u/vulkan.c'
    anchor = 'static VkResult win32u_vkQueuePresentKHR( VkQueue client_queue, const VkPresentInfoKHR *client_present_info )'
    replace(name, anchor,
            'extern uint64_t wine_nx_fex_frame_tick(void);\n'
            'extern void wine_nx_fex_frame_note(uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, int);\n\n' + anchor)
    data = read(name)
    first = data.index(anchor)
    last = data.index('\nstatic LARGE_INTEGER *get_nt_timeout', first)
    old = data[first:last]
    new = old.replace('    TRACE( "queue %p, present_info %p\\n", queue, present_info );',
                      '    uint64_t fex_begin = wine_nx_fex_frame_tick();\n'
                      '    uint64_t fex_lock = 0, fex_host = 0, fex_host_end = 0;\n'
                      '    uint64_t fex_swapchain = present_info->swapchainCount ?\n'
                      '        (uint64_t)present_info->pSwapchains[0] : 0;\n\n'
                      '    TRACE( "queue %p, present_info %p\\n", queue, present_info );')
    new = new.replace('))) return VK_ERROR_OUT_OF_HOST_MEMORY;', '))) goto failed;')
    new = new.replace('    pthread_mutex_lock( &lock );\n'
                      '    res = device->p_vkQueuePresentKHR( queue->host.queue, present_info );\n'
                      '    pthread_mutex_unlock( &lock );',
                      '    fex_lock = wine_nx_fex_frame_tick();\n'
                      '    pthread_mutex_lock( &lock );\n'
                      '    fex_host = wine_nx_fex_frame_tick();\n'
                      '    res = device->p_vkQueuePresentKHR( queue->host.queue, present_info );\n'
                      '    fex_host_end = wine_nx_fex_frame_tick();\n'
                      '    pthread_mutex_unlock( &lock );')
    new = new.replace('    mem_free( &pool );\n    return res;',
                      '    mem_free( &pool );\n'
                      '    wine_nx_fex_frame_note((uint64_t)(uintptr_t)client_queue, fex_swapchain,\n'
                      '                           fex_begin, fex_lock, fex_host, fex_host_end, res);\n'
                      '    return res;')
    assert new.count('wine_nx_fex_frame_tick()') == 4
    assert new.count('wine_nx_fex_frame_note(') == 1
    assert 'return VK_ERROR_OUT_OF_HOST_MEMORY' not in new
    replace(name, old, new)
