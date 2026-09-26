"""Read-only PES timing snapshots and batched periodic diagnostic writes."""


def apply(read, replace, project):
    name = 'wine-nx-probe/source/runtime.c'
    replace(name, 'static int log_flusher_running;',
            (project / 'src/runtime/fex_log_policy.h').read_text() +
            '\nstatic int log_flusher_running;')
    replace(name, 'if (!log_flusher_running || !strncmp(line, "[FEX", 4) || log_line_is_urgent( line ))',
            'if (fex_log_should_flush(line, log_flusher_running, log_line_is_urgent(line)))')
    anchor = 'static void *log_flusher( void *arg )'
    replace(name, anchor,
            (project / 'src/runtime/fex_game_timing.h').read_text() + '\n' +
            (project / 'src/runtime/fex_game_timing_runtime.h').read_text() + '\n' + anchor)
    replace(name, '        ++ticks;\n        if (wine_nx_production',
            '        ++ticks;\n        fex_log_metrics_batch = 1;\n        if (wine_nx_production')
    replace(name, '        if (ticks % 50 == 0) fex_sync_report();',
            '        if (ticks % 50 == 0) fex_sync_report();\n'
            '        if (ticks % 25 == 0) fex_game_timing_report();\n'
            '        fex_log_metrics_batch = 0;')
    # A single existing 5s flush at the end of the iteration commits the batch.
    # Remove only the redundant BOOT flush, not exception or shutdown flushes.
    old = ('                     __atomic_load_n( &wine_nx_fb_frames, __ATOMIC_RELAXED ) );\n'
           '            fflush( log_file );')
    replace(name, old, old.replace('\n            fflush( log_file );', ''))
    replace(name, '    pes13_fex_set_performance_profile(fex_profile);',
            '    pes13_fex_set_performance_profile(fex_profile);\n'
            '    fex_game_timing_enabled = !guest_tests &&\n'
            '        wine_nx_config_file_bool(RUNTIME_DIR "/fex-game-timing.txt", 0);\n'
            '    log_line("[FEX3-GAME] enabled=%d; read-only 5s snapshots, periodic log batching", fex_game_timing_enabled);')
    name = 'dlls/ntdll/unix/virtual.c'
    anchor = 'NTSTATUS virtual_uninterrupted_write_memory( void *addr, const void *buffer, SIZE_T size )'
    replace(name, anchor, '''/* Native diagnostic reader: no TEB, SEH, server request or guest write.
 * The existing helper locks virtual_mutex and checks each page's read access.
 * A short read is rejected, including ranges straddling inaccessible pages. */
int wine_nx_fex_timing_read(uint32_t address, void *out, size_t size)
{
    if (!address || !size || size > 4096 || size > UINT32_MAX - address) return 0;
    return virtual_uninterrupted_read_memory((const void *)(uintptr_t)address, out, size) == size;
}

''' + anchor)
