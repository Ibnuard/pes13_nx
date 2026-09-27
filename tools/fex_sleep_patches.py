"""Relative sleep deadline correction and bounded live self-wait ages."""


def apply(read, replace, project):
    name = 'dlls/ntdll/unix/sync.c'
    anchor = 'static NTSTATUS fex_delay_impl( BOOLEAN alertable, const LARGE_INTEGER *timeout )'
    replace(name, anchor, '#ifdef __SWITCH__\n' +
            (project/'src/runtime/fex_relative_delay.h').read_text() + '\n#endif\n\n' + anchor)
    # This runs only after alertable and infinite branches, before the old
    # wall-time conversion/yield. Zero and absolute waits keep their behavior.
    replace(name, '        timeout_t when, diff;\n\n        if ((when = timeout->QuadPart) < 0)',
            '        timeout_t when, diff;\n\n'
            '#ifdef __SWITCH__\n'
            '        if (timeout->QuadPart < 0)\n'
            '            return fex_relative_delay(0ULL - (ULONGLONG)timeout->QuadPart);\n'
            '#endif\n\n'
            '        if ((when = timeout->QuadPart) < 0)')

    name = 'dlls/ntdll/unix/horizon.c'
    replace(name, '    struct horizon_server_object *object;\n    pthread_cond_t condition;\n};',
            '    struct horizon_server_object *object;\n    pthread_cond_t condition;\n'
            '    uint64_t parked_at;\n};')
    replace(name, '        .next = fex_resume_waiters, .object = object,\n',
            '        .next = fex_resume_waiters, .object = object,\n'
            '        .parked_at = horizon_interrupt_time(),\n')
    replace(name, '    uint64_t now[9];\n    char line[384];',
            '    uint64_t now[9];\n'
            '    struct { unsigned tid, suspend; uint64_t age_us; } rows[16];\n'
            '    struct fex_resume_waiter *waiter;\n'
            '    unsigned count = 0, i;\n'
            '    uint64_t tick;\n'
            '    char line[384];')
    replace(name, '    if (reported && !memcmp(previous, now, sizeof(now))) {',
            '    if (reported && !now[8] && !memcmp(previous, now, sizeof(now))) {')
    replace(name, '    memcpy(previous, now, sizeof(now));\n    reported = 1;',
            '    tick = horizon_interrupt_time();\n'
            '    for (waiter = fex_resume_waiters; waiter && count < 16; waiter = waiter->next) {\n'
            '        rows[count].tid = waiter->object->thread.tid;\n'
            '        rows[count].suspend = waiter->object->thread.suspend;\n'
            '        rows[count].age_us = (tick - waiter->parked_at) / 10;\n'
            '        ++count;\n'
            '    }\n'
            '    memcpy(previous, now, sizeof(now));\n    reported = 1;')
    replace(name, '             (unsigned long long)now[8]);\n    wine_nx_runtime_trace(line);',
            '             (unsigned long long)now[8]);\n    wine_nx_runtime_trace(line);\n'
            '    for (i = 0; i < count; ++i) {\n'
            '        snprintf(line, sizeof(line), "[FEX3-WAIT] tid=%u suspend=%u parked_us=%llu",\n'
            '                 rows[i].tid, rows[i].suspend, (unsigned long long)rows[i].age_us);\n'
            '        wine_nx_runtime_trace(line);\n'
            '    }')

    name = 'wine-nx-probe/source/runtime.c'
    replace(name, '"pes13-fex3-jit-latency"', '"pes13-fex3-sleep-deadline"')
    replace(name, '    log_line("[FEX3-WARM] v1',
            '    log_line("[FEX3-SLEEP] v1 monotonic relative deadlines; no pre-sleep yield; zero/APC waits preserved");\n'
            '    log_line("[FEX3-WARM] v1')
    replace(name, '        fex_log_metrics_batch = 0;\n'
                  '        if (ticks % 50 == 0) wine_nx_fex_resume_report();',
            '        if (ticks % 50 == 0) wine_nx_fex_resume_report();\n'
            '        fex_log_metrics_batch = 0;')
    # Continue existing coarse thread/progress reporting into late-game slow
    # states; never pause threads or enable the statistical profiler.
    replace(name, '(wine_nx_production && (ticks <= 600 ? ticks % 25 == 0 : ticks % 300 == 0))',
            '(wine_nx_production && ticks % 25 == 0)')
