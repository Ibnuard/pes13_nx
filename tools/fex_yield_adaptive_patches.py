"""Reduce persistent guest polling after the validated initial 64-yield burst."""


def apply(read, replace, project):
    name = 'dlls/ntdll/unix/sync.c'
    replace(name, 'extern int wine_nx_fex_yield_backoff;',
            '#include "' + str(project/'src/runtime/fex_yield_adaptive.h') + '"\n'
            'extern int wine_nx_fex_yield_adaptive;\n'
            'extern void wine_nx_fex_yield_adaptive_note(int, int);\n'
            'extern int wine_nx_fex_yield_backoff;')
    replace(name, '        static __thread struct fex_yield_burst burst;',
            '        static __thread struct fex_yield_burst burst;\n'
            '        static __thread struct fex_yield_adaptive adaptive;')
    replace(name, '        if (fex_yield_pause_due(&burst, begin, end)) {',
            '        const int mode = wine_nx_fex_yield_adaptive\n'
            '            ? fex_yield_adaptive_due(&adaptive, begin, end)\n'
            '            : fex_yield_pause_due(&burst, begin, end);\n'
            '        if (mode) {')
    replace(name, '            svcSleepThread(50000); /* 50us after 64 ineffective yields within 2ms */\n'
                  '            const ULONGLONG elapsed_us = (monotonic_counter() - pause_begin) / 10;',
            '            svcSleepThread(50000); /* duration unchanged; sustained polling uses shorter bursts */\n'
            '            const ULONGLONG pause_end = monotonic_counter();\n'
            '            const ULONGLONG elapsed_us = (pause_end - pause_begin) / 10;\n'
            '            if (wine_nx_fex_yield_adaptive)\n'
            '                wine_nx_fex_yield_adaptive_note(mode == 2,\n'
            '                    fex_yield_adaptive_complete(&adaptive, pause_begin, pause_end));')
    name = 'wine-nx-probe/source/runtime.c'
    replace(name, 'static void log_line(const char *fmt, ...);',
            'static void log_line(const char *fmt, ...);\n'
            '#include "' + str(project/'src/runtime/fex_yield_adaptive_runtime.h') + '"')
    replace(name, 'fex_jitlog_report(); fex_yield_report(); }',
            'fex_jitlog_report(); fex_yield_report(); fex_yield_adaptive_report(); }')
    replace(name, '    wine_nx_fex_yield_backoff = wine_nx_config_file_bool(RUNTIME_DIR "/fex_yield_backoff", 1);',
            '    wine_nx_fex_yield_adaptive = wine_nx_config_file_bool(RUNTIME_DIR "/fex_yield_adaptive", 1);\n'
            '    log_line("[FEX3-YIELD-ADAPT] v1 enabled=%d sustained_burst=32 after_good_pauses=4 good_us=100 cooldown_us=5000 if_pause_over_us=200",\n'
            '             wine_nx_fex_yield_adaptive);\n'
            '    wine_nx_fex_yield_backoff = wine_nx_config_file_bool(RUNTIME_DIR "/fex_yield_backoff", 1);')
    replace(name, '[FEX3-YIELD] v1 enabled=%d burst=64', '[FEX3-YIELD] v2 enabled=%d initial_burst=64')
    replace(name, '"pes13-fex3-yield-burst"', '"pes13-fex3-yield-adaptive"')
