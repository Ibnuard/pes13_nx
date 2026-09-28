"""Optional FEX notification routing; shared broadcasts are the recovery default."""
from perf27_patches import function_span


def apply(read, replace, project):
    name = 'dlls/ntdll/unix/horizon.c'
    data = read(name)
    a, b = function_span(data, 'horizon_server_signal_changed_locked')
    replace(name, data[a:b], '#include "' + str(project / 'src/runtime/fex_sync_horizon.h') + '"')
    # Startup, termination, completion ports, messages and unknown changes
    # remain broad. Resume/self-suspend retain the original shared condition.
    for func, count in (('horizon_server_signal_object_locked', 3),
                        ('horizon_server_handle_event_op', 1),
                        ('horizon_server_handle_release_mutex', 1),
                        ('horizon_server_handle_release_semaphore', 1)):
        data = read(name)
        a, b = function_span(data, func)
        old = data[a:b]
        assert old.count('horizon_server_signal_changed_locked();') == count
        replace(name, old, old.replace('horizon_server_signal_changed_locked();',
                                      'fex_sync_signal_object_locked(object);'))
    data = read(name)
    a, b = function_span(data, 'horizon_server_handle_select')
    old = data[a:b]
    new = old.replace('    int polls;', '    int polls;\n    struct pes27_interest interest;')
    anchor = '    polls = horizon_server_select_polls_locked( request, data, data_size );'
    new = new.replace(anchor, anchor + '''
    _Static_assert(offsetof(struct horizon_select_wait_op, handles) == 4, "wait wire offset");
    _Static_assert(offsetof(struct horizon_select_signal_and_wait_op, wait) == 4, "signal wait offset");
    _Static_assert(sizeof(struct horizon_select_signal_and_wait_op) == 12, "signal wait size");
    if (wine_nx_fex_targeted_wake)
        pes27_decode(&interest, data, data_size, request->size, HORIZON_APC_RESULT_SIZE,
            HORIZON_SELECT_WAIT, HORIZON_SELECT_WAIT_ALL, HORIZON_SELECT_SIGNAL_AND_WAIT, connection->thread);''')
    new = new.replace('        horizon_server_sleep_locked( timeout );',
                      '        fex_sync_select_sleep_locked( timeout, &interest );')
    assert new.count('pes27_decode(') == new.count('fex_sync_select_sleep_locked(') == 1
    replace(name, old, new)

    name = 'wine-nx-probe/source/runtime.c'
    anchor = 'static void *log_flusher( void *arg )'
    replace(name, anchor, (project / 'src/runtime/fex_sync_runtime.h').read_text() + '\n' + anchor)
    anchor = '        if (ticks % 50 == 0) { fex_frame_report(); fex_pipeline_report(); }'
    replace(name, anchor, anchor + '\n        if (ticks % 50 == 0) fex_sync_report();')
    anchor = '    pes13_fex_set_performance_profile(fex_profile);'
    replace(name, anchor, anchor + '''
    wine_nx_fex_targeted_wake = wine_nx_config_file_bool(RUNTIME_DIR "/fex-targeted-wake.txt", 0);
    log_line("[FEX3-SYNC] startup targeted=%d; shared start/self-suspend gates preserved", wine_nx_fex_targeted_wake);''')

    # Observe actual sleep/yield wall time by Wine thread, without altering
    # timeout arguments, return status, clocks or the existing sleep policy.
    name = 'dlls/ntdll/unix/sync.c'
    data = read(name)
    a, b = function_span(data, 'NtDelayExecution')
    old = data[a:b]
    assert old.startswith('NTSTATUS WINAPI NtDelayExecution(')
    impl = old.replace('NTSTATUS WINAPI NtDelayExecution(', 'static NTSTATUS fex_delay_impl(', 1)
    wrapper = '''

extern uint64_t wine_nx_fex_frame_tick(void);
extern void wine_nx_fex_delay_note(unsigned, int, int, int64_t, uint64_t, int);
NTSTATUS WINAPI NtDelayExecution(BOOLEAN alertable, const LARGE_INTEGER *timeout)
{
    const int64_t requested = timeout ? timeout->QuadPart : 0;
    uint64_t begin = wine_nx_fex_frame_tick();
    NTSTATUS status = fex_delay_impl(alertable, timeout);
    TEB *teb = NtCurrentTeb();
    if (teb) wine_nx_fex_delay_note((unsigned)(ULONG_PTR)teb->ClientId.UniqueThread,
                                   alertable, !!timeout, requested, begin, status);
    return status;
}
'''
    replace(name, old, impl + wrapper)
