"""Post-hang-audit: reduce routine flushes and measure pipeline/cache warmup."""
import re


def apply(read, replace, project):
    name = 'wine-nx-probe/source/runtime.c'
    anchor = 'static __thread int fex_log_metrics_batch;'
    replace(name, anchor, (project / 'src/runtime/fex_warm_log.h').read_text() + '\n' + anchor)
    anchor = '    return !running || urgent ||\n           (!fex_log_metrics_batch && !strncmp(line, "[FEX", 4));'
    replace(name, anchor,
            '    if (running && !urgent && !fex_log_metrics_batch && fex_warm_routine_line(line)) {\n'
            '        __atomic_add_fetch(&fex_warm_deferred, 1, __ATOMIC_RELAXED);\n'
            '        return 0;\n    }\n' + anchor)
    anchor = 'static void *log_flusher( void *arg )'
    replace(name, anchor, (project / 'src/runtime/fex_warm_runtime.h').read_text() + '\n' + anchor)
    replace(name, 'if (ticks % 50 == 0) { fex_frame_report(); fex_pipeline_report(); }',
            'if (ticks % 50 == 0) { fex_frame_report(); fex_pipeline_report(); fex_warm_report(); }')
    replace(name, '"pes13-fex3-hang-audit"', '"pes13-fex3-warm-audit"')
    anchor = '    log_line("[FEX3-SCALED] no diagnostic readback; blit submit failures propagate");'
    replace(name, anchor, anchor + '\n'
            '    log_line("[FEX3-WARM] v1 routine FEX flush batching; pipeline CPU and driver-cache counters; no persistent FEX cache change");')

    name = 'wine-nx-probe/CMakeLists.txt'
    anchor = 'target_link_options(wine-nx-runtime PRIVATE -Wl,--gc-sections)'
    replace(name, anchor, anchor + '\n'
            'target_link_options(wine-nx-runtime PRIVATE -Wl,--wrap=disk_cache_get)')

    name = 'dlls/winevulkan/vulkan_thunks.c'
    anchor = '#ifdef _WIN64\nstatic NTSTATUS thunk64_vkCreateComputePipelines(void *args)'
    replace(name, anchor, 'extern uint64_t wine_nx_fex_frame_tick(void);\n'
            'extern void wine_nx_fex_compile_note(unsigned, uint64_t, int);\n\n' + anchor)
    calls = re.findall(r'^    params->result = .*?->p_vkCreate(?:Graphics|Compute)Pipelines\([^\n]+;$', read(name), re.M)
    if len(calls) != 4:
        raise ValueError('Warm observer: expected four pipeline creation thunks')
    for call in calls:
        stage = 0 if 'p_vkCreateGraphicsPipelines' in call else 1
        replace(name, call, '    {\n        uint64_t fex_compile_begin = wine_nx_fex_frame_tick();\n' +
                call + '\n        wine_nx_fex_compile_note(' + str(stage) +
                ', fex_compile_begin, params->result);\n    }')
