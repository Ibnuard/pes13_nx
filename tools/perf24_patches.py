"""Bounded CPU sampling and present-gap evidence; math remains PERF23."""
import perf23_patches
from perf17_patches import once


def adapt_recipe(text):
    return once(text, '    vulkan_source.write_text(vulkan_text)',
        '    from perf24_patches import adapt_vulkan\n'
        '    vulkan_text = adapt_vulkan(vulkan_text)\n'
        '    vulkan_source.write_text(vulkan_text)')


def adapt_vulkan(text):
    text=once(text, 'extern unsigned long long wine_nx_perf8_tick(void);',
        'extern unsigned long long wine_nx_perf8_tick(void);\n'
        'extern void wine_nx_perf24_present(void);\n'
        'extern void wine_nx_perf24_host(unsigned long long);')
    text=once(text, '''    if (count && (res == VK_SUCCESS || res == VK_SUBOPTIMAL_KHR))
        __atomic_add_fetch(&wine_nx_vk_successful_presents, 1, __ATOMIC_RELEASE);''',
        '''    if (count && (res == VK_SUCCESS || res == VK_SUBOPTIMAL_KHR)) {
        wine_nx_perf24_present();
        __atomic_add_fetch(&wine_nx_vk_successful_presents, 1, __ATOMIC_RELEASE);
    }''')
    return once(text,
        '        __atomic_add_fetch(&wine_nx_vk_host_present_ticks, wine_nx_perf8_tick() - begin, __ATOMIC_RELAXED);',
        '''        unsigned long long elapsed = wine_nx_perf8_tick() - begin;
        wine_nx_perf24_host(elapsed);
        __atomic_add_fetch(&wine_nx_vk_host_present_ticks, elapsed, __ATOMIC_RELAXED);''')


def adapt(cmake,dynarec,runtime,project):
    cmake,dynarec,runtime=perf23_patches.adapt(cmake,dynarec,runtime,project)
    runtime=once(runtime,'static void log_line(const char *fmt, ...);',
        'static void log_line(const char *fmt, ...);\n#include "'+str(project/'src/runtime/pes13_perf24_runtime.h')+'"')
    runtime=once(runtime,'    wine_nx_thread_report();',
        '    pes24_report();\n    wine_nx_thread_report();')
    runtime=once(runtime,'    if (runtime_profile)\n',
        '''    log_line("[PERF24] present gap bins_us=16667,33334,50000,66667,100000,200000,500000,1000000,2000000,inf; CPU sampler=%s; math flags reported by PERF21/22",
             runtime_profile ? "2s/10s at 20ms" : "off");
    if (runtime_profile)
''')
    return cmake,dynarec,runtime


def adapt_profile(text,project):
    text=perf23_patches.adapt_profile(text,project)
    text=once(text,'#define NX_PROF_PERIOD_NS    10000000',
                   '#define NX_PROF_PERIOD_NS    20000000')
    text=once(text,'static int profiling;',
        'static int profiling;\nunsigned int wine_nx_perf24_sampling_epoch;\n'
        'static uint64_t pes24_pause_ns, pes24_rounds;\n'
        '#include "'+str(project/'src/runtime/pes13_perf24_metrics.h')+'"')
    text=once(text,'    (void)arg;\n    for (;;)',
        '    uint64_t pes24_start = armGetSystemTick();\n'
        '    int pes24_active = 0;\n    (void)arg;\n    for (;;)')
    text=once(text,'''        svcSleepThread( NX_PROF_PERIOD_NS );
        pthread_mutex_lock( &profile_mutex );''',
        '''        svcSleepThread(pes24_active ? NX_PROF_PERIOD_NS : 200000000);
        int active = pes24_sample_window(armTicksToNs(armGetSystemTick()-pes24_start));
        if (active != pes24_active) {
            __atomic_add_fetch(&wine_nx_perf24_sampling_epoch, 1, __ATOMIC_RELEASE);
            pes24_active = active;
        }
        if (!active) continue;
        pthread_mutex_lock( &profile_mutex );
        ++pes24_rounds;''')
    text=once(text,'            if (!target->handle) continue;',
        '            if (!target->handle) continue;\n            uint64_t pause_start = armGetSystemTick();')
    text=once(text,'            svcSetThreadActivity( target->handle, ThreadActivity_Runnable );',
        '            svcSetThreadActivity( target->handle, ThreadActivity_Runnable );\n'
        '            pes24_pause_ns += armTicksToNs(armGetSystemTick()-pause_start);')
    text=once(text,'every %u ms, the %u busiest threads; runtime',
        'every %u ms in 2s/10s bursts, the %u busiest threads; runtime')
    text=once(text,'''    pthread_mutex_lock( &profile_mutex );
    for (i = 0; i < NX_PROF_TARGETS; i++)
    {
        const struct nx_prof_target *target = &targets[i];''',
        '''    pthread_mutex_lock( &profile_mutex );
    {
        static uint64_t last_rounds, last_pause;
        snprintf(line, sizeof(line), "[SAMPLE24] rounds=%llu target_suspend_wall_us=%llu epoch=%u; samples include blocked time",
            (unsigned long long)(pes24_rounds-last_rounds),
            (unsigned long long)((pes24_pause_ns-last_pause)/1000),
            __atomic_load_n(&wine_nx_perf24_sampling_epoch, __ATOMIC_ACQUIRE));
        wine_nx_runtime_trace(line);
        last_rounds=pes24_rounds; last_pause=pes24_pause_ns;
    }
    for (i = 0; i < NX_PROF_TARGETS; i++)
    {
        const struct nx_prof_target *target = &targets[i];''')
    return text
