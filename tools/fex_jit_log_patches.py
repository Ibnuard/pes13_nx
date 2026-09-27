"""Move only known JIT timing reports off game threads; keep error logging intact."""


def apply(read, replace, project):
    name = 'wine-nx-probe/source/runtime.c'
    replace(name, 'static void log_line(const char *fmt, ...);',
            'static void log_line(const char *fmt, ...);\n'
            '#include "' + str(project/'src/runtime/fex_jit_log_queue.h') + '"\n'
            'static int fex_jitlog_sync;\n'
            'static void fex_jitlog_drain(void)\n'
            '{\n'
            '    char line[FEX_JITLOG_BYTES];\n'
            '    for (unsigned i = 0; i < FEX_JITLOG_SLOTS && fex_jitlog_pop(line); ++i) {\n'
            '        log_line("%s", line);\n'
            '        __atomic_add_fetch(&fex_jitlog.written, 1, __ATOMIC_RELAXED);\n'
            '    }\n'
            '}\n'
            'static void fex_jitlog_report(void)\n'
            '{\n'
            '    log_line("[FEX3-JITLOG] queued=%llu written=%llu dropped=%llu; cumulative statistics only",\n'
            '             (unsigned long long)__atomic_load_n(&fex_jitlog.queued, __ATOMIC_RELAXED),\n'
            '             (unsigned long long)__atomic_load_n(&fex_jitlog.written, __ATOMIC_RELAXED),\n'
            '             (unsigned long long)__atomic_load_n(&fex_jitlog.dropped, __ATOMIC_RELAXED));\n'
            '}')
    replace(name, '        fex_log_metrics_batch = 1;',
            '        fex_log_metrics_batch = 1;\n        fex_jitlog_drain();')
    replace(name, '        if (ticks % 50 == 0) fex_sync_report();',
            '        if (ticks % 50 == 0) { fex_sync_report(); fex_jitlog_report(); }')
    replace(name, 'void wine_nx_runtime_trace( const char *msg )\n{\n    log_line( "%s", msg );\n}',
            'void wine_nx_runtime_trace( const char *msg )\n{\n'
            '    if (log_flusher_running && !fex_jitlog_sync && fex_jitlog_enqueue(msg)) return;\n'
            '    log_line( "%s", msg );\n}')
    replace(name, '    wine_nx_fex_auto_core3 = wine_nx_config_file_bool(RUNTIME_DIR "/fex_auto_core3", 0);',
            '    fex_jitlog_sync = wine_nx_config_file_bool(RUNTIME_DIR "/fex_jitlog_sync", 0);\n'
            '    log_line("[FEX3-JITLOG] v1 mode=%s; bounded statistics queue; faults keep original path",\n'
            '             fex_jitlog_sync ? "synchronous-control" : "async");\n'
            '    wine_nx_fex_auto_core3 = wine_nx_config_file_bool(RUNTIME_DIR "/fex_auto_core3", 0);')
    replace(name, '"pes13-fex3-worker-cores"', '"pes13-fex3-camera-720"')
