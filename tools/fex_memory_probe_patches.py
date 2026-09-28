"""Bounded timing of native memory-properties queries; preserve all outputs."""
import re


def apply(read, replace, project):
    name = 'wine-nx-probe/source/runtime.c'
    anchor = 'static void *log_flusher( void *arg )'
    replace(name, anchor, (project/'src/runtime/fex_memory_probe.h').read_text()+'\n'+anchor)
    replace(name, 'fex_yield_report(); fex_gap_report(); }',
            'fex_yield_report(); fex_gap_report(); fex_memory_report(); }')
    anchor = '    log_line("[FEX3-GAP] v1 enabled=%d threshold_us=50000 capacity=32; one thread tick query per Present", fex_gap_probe_enabled);'
    replace(name, anchor, anchor+'\n    log_line("[FEX3-MEMQUERY] v1 enabled=%d threshold_us=1000 capacity=32; native memory-properties2 queries, two CPU queries per call", fex_gap_probe_enabled);')
    replace(name, '"pes13-fextendo-v1"', '"pes13-fextendo-mem-audit"')
    name = 'dlls/winevulkan/vulkan_thunks.c'
    anchor = '#ifdef _WIN64\nstatic NTSTATUS thunk64_vkGetPhysicalDeviceMemoryProperties2(void *args)'
    replace(name, anchor, 'extern uint64_t wine_nx_fex_memory_begin(uint64_t *);\n'
            'extern void wine_nx_fex_memory_end(uint64_t, uint64_t);\n\n'+anchor)
    calls = re.findall(r'^    vulkan_physical_device_from_handle\([^\n]+->p_vkGetPhysicalDeviceMemoryProperties2(?:KHR)?\([^\n]+;$', read(name), re.M)
    if len(calls) != 4:
        raise ValueError('Expected four 32/64-bit core/KHR memory queries, got '+str(len(calls)))
    for call in calls:
        replace(name, call, '    {\n        uint64_t fex_memory_cpu;\n'
                '        uint64_t fex_memory_begin = wine_nx_fex_memory_begin(&fex_memory_cpu);\n'+call+'\n'
                '        wine_nx_fex_memory_end(fex_memory_begin, fex_memory_cpu);\n    }')
