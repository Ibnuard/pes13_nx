"""Keep automatic Wine workers on cores 0-2; explicit guest affinity wins."""


def apply(read, replace, project):
    header = '#include "' + str(project/'src/runtime/fex_worker_cores.h') + '"\n'
    name = 'dlls/ntdll/unix/horizon.c'
    replace(name, 'void horizon_pin_current_thread( ULONG_PTR requested_mask )',
            header + '\nvoid horizon_pin_current_thread( ULONG_PTR requested_mask )')
    replace(name, '        unsigned int count = horizon_get_processor_count();\n\n'
                  '        index = InterlockedIncrement( &next_core_index ) - 1;\n'
                  '        mask = nth_core_mask( system_mask, index % count );',
            '        const ULONG_PTR automatic = fex_auto_worker_mask(system_mask, wine_nx_fex_auto_core3);\n'
            '        unsigned int count = count_mask_bits( automatic );\n\n'
            '        index = InterlockedIncrement( &next_core_index ) - 1;\n'
            '        mask = nth_core_mask( automatic, index % count );')

    name = 'wine-nx-probe/source/thread_profile.c'
    replace(name, '#include "thread_profile.h"', '#include "thread_profile.h"\n' + header)
    replace(name, '    for (i = 0; i < 64 && cores < NX_BALANCE_MAX_CORES; i++)',
            '    process_mask = fex_auto_worker_mask(process_mask, wine_nx_fex_auto_core3);\n'
            '    for (i = 0; i < 64 && cores < NX_BALANCE_MAX_CORES; i++)')
    # Keep the existing THREADS line parseable. Snapshot the actual mask and
    # explicit-affinity bit alongside its existing syscall; log after unlock.
    replace(name, '    uint64_t teb;\n};\n\nstruct nx_prof_target',
            '    uint64_t teb;\n    uint64_t core_mask;\n    int fixed;\n};\n\nstruct nx_prof_target')
    replace(name, '        if (R_FAILED( svcGetThreadCoreMask( &row.core, &mask, thread->handle ) )) row.core = thread->core;',
            '        row.fixed = thread->fixed;\n'
            '        row.core_mask = 0; /* zero means unavailable, not an affinity request */\n'
            '        if (R_FAILED( svcGetThreadCoreMask( &row.core, &mask, thread->handle ) )) row.core = thread->core;\n'
            '        else row.core_mask = mask;')
    replace(name, '    wine_nx_runtime_trace( line );\n    server_report();',
            '    wine_nx_runtime_trace( line );\n'
            '    len = appendf( line, 0, "[FEX3-COREMAP]" );\n'
            '    for (i = 0; i < count && i < 12 && rows[i].permille >= 5; i++)\n'
            '        if (rows[i].kind == \'w\')\n'
            '            len = appendf( line, len, " %u:mask=%llx,fixed=%d", rows[i].tid,\n'
            '                           (unsigned long long)rows[i].core_mask, rows[i].fixed );\n'
            '    wine_nx_runtime_trace( line );\n'
            '    server_report();')

    name = 'wine-nx-probe/source/runtime.c'
    replace(name, 'static int log_flusher_running;',
            '/* Only placement policy; do not change guest processor count or time. */\n'
            'int wine_nx_fex_auto_core3;\nstatic int log_flusher_running;')
    replace(name, '    if (wine_nx_config_file_bool(RUNTIME_DIR "/no-balance.txt", 0)) wine_nx_balance_enabled = 0;',
            '    wine_nx_fex_auto_core3 = wine_nx_config_file_bool(RUNTIME_DIR "/fex_auto_core3", 0);\n'
            '    log_line("[FEX3-CORES] v1 automatic=%s; explicit guest affinity preserved",\n'
            '             wine_nx_fex_auto_core3 ? "all granted cores (control)" : "prefer 0-2 (fallback if unavailable)");\n'
            '    if (wine_nx_config_file_bool(RUNTIME_DIR "/no-balance.txt", 0)) wine_nx_balance_enabled = 0;')
    replace(name, '"pes13-fex3-sleep-deadline"', '"pes13-fex3-worker-cores"')
