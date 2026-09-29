"""Shorten validated two-argument native gateways; retain every Wine handler."""


def apply(read, replace, project):
    name = 'dlls/ntdll/unix/signal_arm64.c'
    anchor = '#include "' + str(project/'src/runtime/fex_polling_counters.h') + '"'
    replace(name, anchor, anchor + '\n#include "' + str(project/'src/runtime/fex_fast_api.h') + '"')
    replace(name, '    "__wine_syscall_dispatcher:\\n"',
            '    "__wine_syscall_dispatcher:\\n"\n    FEX_FAST_API_ENTRY')
    name = 'wine-nx-probe/source/runtime.c'
    anchor = '    extern int wine_nx_fex_polling;'
    replace(name, anchor, '''    extern int wine_nx_fex_fast_api;
    wine_nx_fex_fast_api = !guest_tests && wine_nx_config_file_bool(RUNTIME_DIR "/fex_fast_api", 1);
    log_line("[FEX3-FASTAPI] v1 enabled=%d QPC/delay native gateway; live handler check; original clock, APC and deadlines", wine_nx_fex_fast_api);
''' + anchor)
    anchor = '        wine_nx_fex_poll_totals(poll_counts);'
    replace(name, anchor, anchor + '''
        extern void wine_nx_fex_fast_api_totals(unsigned out[2]);
        unsigned fast_counts[2];
        wine_nx_fex_fast_api_totals(fast_counts);
        log_line("[FEX3-FASTAPI] qpc=%u delay=%u cumulative registered-slot calls", fast_counts[0], fast_counts[1]);''')
    replace(name, '"pes13-fextendo-polling-v1"', '"pes13-fextendo-fast-api-v1"')
    anchor='    log_line( "[INIT] profiler %s (profile.txt)", runtime_profile ? "on" : "off" );'
    replace(name,anchor,'''    /* Dedicated FEX sampler opt-in overrides inherited Box64 profile flags. */
    runtime_profile = !guest_tests && wine_nx_config_file_bool(RUNTIME_DIR "/fex_hot_profile", 0);
    log_line("[FEX3-HOT] enabled=%d sample_period_ms=50 targets=2; sampled residency includes waits; diagnostic only", runtime_profile);
''' + anchor)
    name='wine-nx-probe/source/thread_profile.c'
    replace(name,'#define NX_PROF_TARGETS      4','#define NX_PROF_TARGETS      2')
    replace(name,'#define NX_PROF_PERIOD_NS    2000000','#define NX_PROF_PERIOD_NS    50000000')
    replace(name,'static int profiling;', '''static int profiling;
static int fex_hot_pc(const ThreadContext *, uintptr_t *);
static uint64_t fex_hot_pauses, fex_hot_pause_ticks, fex_hot_peak_ticks, fex_hot_resume_failures;''')
    replace(name,'            if (!target->handle) continue;\n            if (R_FAILED( svcSetThreadActivity',
            '            if (!target->handle) continue;\n            const uint64_t fex_pause_begin=armGetSystemTick();\n            if (R_FAILED( svcSetThreadActivity')
    replace(name,'            for (tries = 0; R_FAILED( rc = svcGetThreadContext3( &ctx, target->handle ) ) && tries < 4; tries++)',
            '            for (tries = 0; R_FAILED( rc = svcGetThreadContext3( &ctx, target->handle ) ) && tries < 1; tries++)')
    replace(name,'''                if (&wine_nx_box64_pc_to_x86) translated = wine_nx_box64_pc_to_x86( ctx.pc.x, &x86 );
                x86_count = translated ? walk_x86_frames( &ctx, x86_callers ) : walk_x86( target->teb, x86_callers );''',
            '''                translated = fex_hot_pc(&ctx, &x86);
                /* Box64's guest-register and stack conventions do not apply. */
                x86_count = 0;''')
    replace(name,'            svcSetThreadActivity( target->handle, ThreadActivity_Runnable );',
            '''            Result resumed=svcSetThreadActivity(target->handle,ThreadActivity_Runnable);
            if (R_FAILED(resumed)) resumed=svcSetThreadActivity(target->handle,ThreadActivity_Runnable);
            if (R_FAILED(resumed)) ++fex_hot_resume_failures;
            const uint64_t paused=armGetSystemTick()-fex_pause_begin;
            ++fex_hot_pauses; fex_hot_pause_ticks+=paused;
            if (paused>fex_hot_peak_ticks) fex_hot_peak_ticks=paused;''')
    replace(name,'    if (kind == NX_PROF_X86) key = x86 & ~0x1full;',
            '    if (kind == NX_PROF_X86) key = x86; /* FEX compilation-unit entry */')
    anchor='    unsigned int i, j, k, shown, top[12];\n    int len;\n\n    pthread_mutex_lock( &profile_mutex );'
    replace(name,anchor,anchor+'''
    snprintf(line,sizeof(line),"[FEX3-HOT] pauses=%llu pause_us=%llu peak_us=%llu resume_failures=%llu tick=%llu",
        (unsigned long long)fex_hot_pauses,(unsigned long long)(armTicksToNs(fex_hot_pause_ticks)/1000),
        (unsigned long long)(armTicksToNs(fex_hot_peak_ticks)/1000),(unsigned long long)fex_hot_resume_failures,
        (unsigned long long)armGetSystemTick());
    wine_nx_runtime_trace(line);''')
    anchor='#include "horizon_stall.h"'
    replace(name,anchor,anchor+'\nstatic int fex_stall_read(uint64_t, void *, size_t);\n#include "'+str(project/'src/runtime/fex_hot_profile.h')+'"')
