"""Bounded secondary balancing and persistent launch history for PERF23."""
from perf17_patches import once

def adapt_profile(text, project):
    text=once(text,'#include "thread_profile.h"',
        '#include "thread_profile.h"\n#include "'+str(project/'src/runtime/pes13_perf23_balance.h')+'"')
    text=once(text,'int wine_nx_balance_enabled = 1;',
        'int wine_nx_balance_enabled = 1;\nint wine_nx_perf23_balance;')
    text=once(text,'    s32 core;\n    uint64_t teb;\n};',
        '    s32 core;\n    uint64_t teb, mask;\n    int fixed;\n};')
    text=once(text,'        if (R_FAILED( svcGetThreadCoreMask( &row.core, &mask, thread->handle ) )) row.core = thread->core;',
        '''        mask = 0;
        if (R_FAILED( svcGetThreadCoreMask( &row.core, &mask, thread->handle ) )) row.core = thread->core;
        row.mask = mask;
        row.fixed = thread->fixed;''')
    text=once(text,'    wine_nx_runtime_trace( line );\n    server_report();',
        '''    wine_nx_runtime_trace( line );
    len = appendf(line, 0, "[AFF23] top-thread masks/fixed:");
    for (i = 0; i < count && i < 8 && rows[i].permille >= 5; i++)
        len = appendf(line, len, " %u%c=0x%llx/%d", rows[i].tid, rows[i].kind,
                      (unsigned long long)rows[i].mask, rows[i].fixed);
    wine_nx_runtime_trace(line);
    server_report();''')
    text=once(text,'void wine_nx_thread_balance( void )\n{\n    static u64 last;',
        'void wine_nx_thread_balance( void )\n{\n    static u64 last, last_secondary;')
    text=once(text,'    int len, urgent = 0;',
        '    int len, urgent = 0, secondary = 0, secondary_moved = 0;\n    uint64_t secondary_gain = 0;')
    old='''    if (!urgent && after + 5 * NX_BALANCE_SLACK / 3 >= before)
    {
        pthread_mutex_unlock( &registry_mutex );
        return;
    }
    len = appendf( line, 0, "[BALANCE] busiest core %u.%u%% -> %u.%u%%:", before / 10, before % 10, after / 10, after % 10 );'''
    new='''    if (!urgent && after + 5 * NX_BALANCE_SLACK / 3 >= before)
    {
        /* The peak can remain owned by an unrelated busy thread while a
         * secondary core has two contenders and another core is idle. */
        if (!__atomic_load_n(&wine_nx_perf23_balance, __ATOMIC_ACQUIRE) ||
            (last_secondary && armTicksToNs(now - last_secondary) < 4000000000ull) ||
            !(secondary = pes23_secondary_move(balance, count, cores, &secondary_gain)))
        {
            pthread_mutex_unlock( &registry_mutex );
            return;
        }
        last_secondary = now;
    }
    if (secondary)
        len = appendf(line, 0, "[BALANCE23] secondary-core split peak_before=%u.%u%% load_square_gain=%llu:",
                      before / 10, before % 10, (unsigned long long)secondary_gain);
    else
        len = appendf( line, 0, "[BALANCE] busiest core %u.%u%% -> %u.%u%%:", before / 10, before % 10, after / 10, after % 10 );'''
    text=once(text,old,new)
    text=once(text,'        /* Still registered, so its TEB is still there. */',
        '        if (secondary) secondary_moved = 1;\n        /* Still registered, so its TEB is still there. */')
    return once(text,'    pthread_mutex_unlock( &registry_mutex );\n    wine_nx_runtime_trace( line );\n}',
        '    pthread_mutex_unlock( &registry_mutex );\n    if (!secondary || secondary_moved) wine_nx_runtime_trace( line );\n}')

def adapt(cmake,dynarec,runtime,project):
    runtime=once(runtime,'static FILE *log_file;',
        '#include "'+str(project/'src/runtime/pes13_perf23_logs.h')+'"\nstatic FILE *log_file;\nstatic int pes23_rotation_error;')
    runtime=once(runtime,'    log_file = fopen( RUNTIME_DIR "/pes13-nx.log", "w" );',
        '    log_file = pes23_open_log(RUNTIME_DIR, &pes23_rotation_error);')
    runtime=once(runtime,'        setvbuf( log_file, log_file_buffer, _IOFBF, sizeof(log_file_buffer) );',
        '''        setvbuf( log_file, log_file_buffer, _IOFBF, sizeof(log_file_buffer) );
        fprintf(log_file, "[RUN23] new launch; previous-1 is newest; retained=4 rotation_errno=%d\\n", pes23_rotation_error);
        fflush(log_file);''')
    runtime=once(runtime,'    log_line( "[INIT] core balancing %s (no-balance.txt)", wine_nx_balance_enabled ? "on" : "off" );',
        '''    log_line( "[INIT] core balancing %s (no-balance.txt)", wine_nx_balance_enabled ? "on" : "off" );
    {
        extern int wine_nx_perf23_balance;
        int enabled = read_bool_file(RUNTIME_DIR "/perf23-balance.txt");
        __atomic_store_n(&wine_nx_perf23_balance, enabled, __ATOMIC_RELEASE);
        log_line("[PERF23] secondary_balance=%d history=4 math_policy=PERF22 SAFEFLAGS=unchanged", enabled);
    }''')
    # No sampler or additional work on each rendered frame. This coarse
    # heartbeat records absent progress in the existing ten-second report.
    runtime=once(runtime,'    static unsigned int last_frames, last_host_calls;',
        '    static unsigned int last_frames, last_host_calls, quiet_intervals;')
    runtime=once(runtime,'        unsigned int delta = frames - last_frames, calls = host_calls - last_host_calls;',
        '''        unsigned int delta = frames - last_frames, calls = host_calls - last_host_calls;
        quiet_intervals = delta ? 0 : quiet_intervals + 1;
        if (quiet_intervals >= 2)
            log_line("[WATCH23] no presents for %u report intervals; total_presents=%u host_calls=%u; not a deadlock verdict", quiet_intervals, frames, calls);''')
    return cmake,dynarec,runtime
