"""Bound dense ineffective nonalertable Sleep(0)/SwitchToThread polling."""


def apply(read, replace, project):
    name = 'dlls/ntdll/unix/sync.c'
    replace(name, 'NTSTATUS WINAPI NtYieldExecution(void)',
            '#ifdef __SWITCH__\n'
            '#include "' + str(project/'src/runtime/fex_yield_burst.h') + '"\n'
            'extern int wine_nx_fex_yield_backoff;\n'
            'extern void wine_nx_fex_yield_pause_note(unsigned, uint64_t);\n'
            '#endif\n\nNTSTATUS WINAPI NtYieldExecution(void)')
    replace(name, '    svcSleepThread( 0 );  /* YieldType_WithoutCoreMigration: FEX Sleep(0) */',
            '    if (wine_nx_fex_yield_backoff) {\n'
            '        static __thread struct fex_yield_burst burst;\n'
            '        const ULONGLONG begin = monotonic_counter();\n'
            '        svcSleepThread(0);\n'
            '        const ULONGLONG end = monotonic_counter();\n'
            '        if (fex_yield_pause_due(&burst, begin, end)) {\n'
            '            const ULONGLONG pause_begin = monotonic_counter();\n'
            '            svcSleepThread(50000); /* 50us after 64 ineffective yields within 2ms */\n'
            '            const ULONGLONG elapsed_us = (monotonic_counter() - pause_begin) / 10;\n'
            '            TEB *teb = NtCurrentTeb();\n'
            '            if (teb) wine_nx_fex_yield_pause_note((unsigned)(ULONG_PTR)teb->ClientId.UniqueThread, elapsed_us);\n'
            '        }\n'
            '    } else svcSleepThread(0);')
    name = 'wine-nx-probe/source/runtime.c'
    replace(name, 'static void log_line(const char *fmt, ...);',
            'static void log_line(const char *fmt, ...);\n'
            '#include "' + str(project/'src/runtime/fex_yield_runtime.h') + '"')
    replace(name, '        if (ticks % 50 == 0) { fex_sync_report(); fex_jitlog_report(); }',
            '        if (ticks % 50 == 0) { fex_sync_report(); fex_jitlog_report(); fex_yield_report(); }')
    replace(name, '    fex_jitlog_sync = wine_nx_config_file_bool(RUNTIME_DIR "/fex_jitlog_sync", 0);',
            '    wine_nx_fex_yield_backoff = wine_nx_config_file_bool(RUNTIME_DIR "/fex_yield_backoff", 1);\n'
            '    log_line("[FEX3-YIELD] v1 enabled=%d burst=64 window_us=2000 ineffective_us=2 pause_us=50",\n'
            '             wine_nx_fex_yield_backoff);\n'
            '    fex_jitlog_sync = wine_nx_config_file_bool(RUNTIME_DIR "/fex_jitlog_sync", 0);')
    replace(name, '"pes13-fex3-camera-720"', '"pes13-fex3-yield-burst"')
