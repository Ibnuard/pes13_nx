"""Production-only logging removal; leave maintenance and game I/O intact."""


def apply(read, replace, project):
    runtime = 'wine-nx-probe/source/runtime.c'

    def body(name, signature, replacement):
        text = read(name)
        assert text.count(signature) == 1, signature
        begin = text.index(signature) + len(signature)
        start = text.index('{', begin)
        # These complete function bodies contain no unmatched braces in literals.
        depth = 1
        end = start + 1
        while depth:
            depth += (text[end] == '{') - (text[end] == '}')
            end += 1
        replace(name, text[start:end], '{\n' + replacement + '\n}')

    replace(runtime, '#include "wine_bridge.h"', '#include "wine_bridge.h"\n' +
            '#include "' + str(project / 'src/runtime/fextendo_silent_io.h') + '"')
    replace(runtime, '"pes13-fextendo-fast-api-v1"', '"pes13-fextendo-production-no-log-v2"')
    body(runtime, 'static void log_line( const char *fmt, ... )\n', '    (void)fmt;')
    body(runtime, 'void wine_nx_runtime_trace( const char *msg )\n', '    (void)msg;')
    body(runtime, 'static FILE *fx_open_log(const char *directory, int *rotation_error)\n',
         '    (void)directory; *rotation_error = 0; return NULL;')
    body(runtime, 'void wine_nx_runtime_std_write( int stream, const char *data, size_t size )\n',
         '    (void)stream; (void)data; (void)size;')
    body(runtime, 'void wine_nx_runtime_dump_std_streams(void)\n',
         '    /* No diagnostics or inspection of old stdio log files on exit. */')
    body(runtime, 'static void *log_flusher( void *arg )\n', '''    unsigned ticks = 0;
    (void)arg;
    for (;;) {
        svcSleepThread(200000000LL);
        fx_production_maintenance_tick(++ticks);
    }
    return NULL;''')
    replace(runtime, 'static void *log_flusher( void *arg )\n', '''/* Registry persistence and CPU balancing also lived in the logger.
 * Keep their cadence, without diagnostic sampling, queue draining or SD logs. */
void __attribute__((noinline)) fx_production_maintenance_tick(unsigned ticks)
{
    extern int horizon_registry_flush(void);
    if (ticks % 5 == 0) horizon_registry_flush();
    if (ticks % 10 == 0) wine_nx_thread_balance();
    runtime_alternate_clean();
}

static void *log_flusher( void *arg )
''')
    old = '''    int rotation_error = 0;
    log_file = fx_open_log(RUNTIME_DIR, &rotation_error);
    if (log_file)
    {
        pthread_t flusher;

        setvbuf( log_file, log_file_buffer, _IOFBF, sizeof(log_file_buffer) );
        fprintf(log_file, "[FEXTENDO] session_start version=%s release=%s phase=launcher rotation_errno=%d; previous runs: fex-runtime.previous-1.log through previous-4.log\\n", FX_APP_VERSION, FX_RELEASE, rotation_error);
        fflush(log_file);
        log_flusher_running = !pthread_create( &flusher, NULL, log_flusher, NULL );
    }'''
    replace(runtime, old, '''    /* Start required maintenance independently of a log file. */
    pthread_t maintenance;
    if (pthread_create(&maintenance, NULL, log_flusher, NULL)) {
        fx_native_error("Unable to start runtime maintenance. Close and relaunch.");
        return 1;
    }
    pthread_detach(maintenance);''')
    replace(runtime, '    int sd_cache = wine_nx_sd_cache_install();',
            '    if (!fx_silent_io_init()) return 1;\n'
            '    setenv("WINEDEBUG", "-all", 1);\n'
            '    int sd_cache = wine_nx_sd_cache_install();')
    # Force diagnostics off even when legacy files or an existing INI enable them.
    replace(runtime, '    wine_nx_config_key(key, sizeof(key), legacy_path);',
            '''    wine_nx_config_key(key, sizeof(key), legacy_path);
    static const char *const disabled[] = {
        "run_guest_tests", "verbose", "profile", "controller_trace", "controller_test",
        "vulkan_probe", "fex_hot_profile", "fex_gap_probe", "fex_jitlog_sync",
        "fex_game_timing", "fex_event_diagnostic"
    };
    for (unsigned j = 0; j < sizeof(disabled) / sizeof(disabled[0]); ++j)
        if (!strcmp(key, disabled[j])) return 0;
    if (!strcmp(key, "fex_short_trace_off") || !strcmp(key, "production")) return 1;''')
    replace(runtime, 'if (settings.verbose >= 0) wine_nx_runtime_verbose = settings.verbose;',
            'wine_nx_runtime_verbose = 0;')
    replace(runtime, 'if (settings.profile >= 0) runtime_profile = settings.profile;',
            'runtime_profile = 0;')
    replace(runtime, '''        options[0].flags = (1 << __WINE_DBCL_ERR) |
                           (wine_nx_runtime_verbose ? (1 << __WINE_DBCL_FIXME) | (1 << __WINE_DBCL_WARN) : 0);''',
            '        options[0].flags = 0;')
    for name in ('stdin', 'stdout', 'stderr'):
        replace(runtime, 'RUNTIME_DIR "/' + name + '.txt", GENERIC_', 'FX_NULL_PATH, GENERIC_')
    # Appended at the one shared environment handoff, including WineD3D fallback.
    replace(runtime, 'const char trace_key[] = "FEXTENDO_TRACE=0";',
            'const char trace_key[] = "FEXTENDO_TRACE=0\\0DXVK_LOG_LEVEL=none\\0DXVK_LOG_PATH=none\\0WINEDEBUG=-all";')
    replace(runtime, '''            if (__atomic_load_n(&fex_short_enabled, __ATOMIC_ACQUIRE))
                short_environment[environment_bytes + sizeof(trace_key) - 3] = '1';''',
            '            /* Production never enables guest diagnostics. */')
    replace(runtime, 'Fextendo could not start PES13. Check fex-runtime.log, then close and relaunch.',
            'Fextendo could not start PES13. Check the game and runtime files, then close and relaunch.')
    replace(runtime, 'PES13 could not start. Check fex-runtime.log.',
            'PES13 could not start. Check the game and runtime files.')
    body('dlls/ntdll/unix/horizon.c', 'void horizon_trace( const char *fmt, ... )\n', '    (void)fmt;')
    debug = 'dlls/ntdll/unix/debug.c'
    # The custom Horizon entry does not initialize upstream Wine main_argv.
    # WINEDEBUG (including -all) would otherwise dereference main_argv[1]
    # during the first lazy channel lookup, before the guest can start.
    body(debug, 'static void init_options(void)\n', '''    /* Production has no debug options to parse, including during early boot. */
    nb_debug_options = 0;
    default_flags = 0;''')
    body(debug, 'unsigned char __cdecl __wine_dbg_get_channel_flags( struct __wine_debug_channel *channel )\n',
         '    channel->flags = 0;\n    return 0;')
    body(debug, 'static int wine_nx_dbg_write( const char *str, unsigned int str_len )\n',
         '    (void)str; return str_len;')
    body(debug, 'int __cdecl __wine_dbg_output( const char *str )\n',
         '    return strlen(str);')
    body(debug, 'static void __wine_dbg_ftrace_write( const char *str, unsigned int str_len )\n',
         '    (void)str; (void)str_len;')
