"""Bounded short-stall observations on the unchanged v3.2 runtime policy."""
from fex_resume_patches import _function


def apply(read, replace, project):
    name = 'wine-nx-probe/source/runtime.c'
    anchor = 'static void log_line(const char *fmt, ...);'
    replace(name, anchor, anchor+'\n#include "'+str(project/'src/runtime/fex_short_trace.h')+'"')
    replace(name, '        fex_jitlog_drain();', '        fex_jitlog_drain();\n        fex_short_drain();')
    replace(name, 'fex_sync_report(); fex_jitlog_report();', 'fex_sync_report(); fex_jitlog_report(); fex_short_report();')
    replace(name, '    if (log_flusher_running && !fex_jitlog_sync && fex_jitlog_enqueue(msg)) return;',
            '    if (fex_short_enqueue_text(msg)) return;\n'
            '    if (log_flusher_running && !fex_jitlog_sync && fex_jitlog_enqueue(msg)) return;')
    replace(name, '    /* Existing profiler uses the same kernel counter, in system-tick units. */',
            '    fex_short_present_map();\n    /* Existing profiler uses the same kernel counter, in system-tick units. */')
    replace(name, '    fex_gap_pipeline_note(stage, armTicksToNs(end - begin) / 1000);',
            '    fex_gap_pipeline_note(stage, armTicksToNs(end - begin) / 1000);\n'
            '    wine_nx_fex_short_stage(stage, begin, end, 0, result);')
    anchor = '    const int guest_tests = wine_nx_config_file_bool(RUNTIME_DIR "/run-guest-tests.txt", 0);'
    replace(name, anchor, anchor+'\n'
            '    __atomic_store_n(&fex_short_enabled, !guest_tests && log_flusher_running &&\n'
            '        !wine_nx_config_file_bool(RUNTIME_DIR "/fex_short_trace_off", 0), __ATOMIC_RELEASE);\n'
            '    log_line("[FEX3-SHORT] v1 enabled=%d threshold_us=20000 rows=256 jit_rows=128; fex_short_trace_off=1 disables; kinds 0=acquire 1=submit 2=fence 3=semaphore 5=alert_wait 6=present_map", fex_short_enabled);')
    # Preserve all existing environment entries and their double-NUL terminator.
    replace(name, '    chars += environment_bytes;', '''    {
        static char short_environment[8192];
        const char trace_key[] = "FEXTENDO_TRACE=0";
        if (environment_bytes && environment_bytes + sizeof(trace_key) <= sizeof(short_environment)) {
            memcpy(short_environment, environment, environment_bytes);
            memcpy(short_environment + environment_bytes - 1, trace_key, sizeof(trace_key));
            if (__atomic_load_n(&fex_short_enabled, __ATOMIC_ACQUIRE))
                short_environment[environment_bytes + sizeof(trace_key) - 3] = '1';
            environment_bytes += sizeof(trace_key);
            short_environment[environment_bytes - 1] = 0;
            environment = short_environment;
        }
    }
    chars += environment_bytes;''')
    replace(name, '"pes13-fextendo-v3.2-glass"', '"pes13-fextendo-short-trace-v1"')
    name = 'dlls/ntdll/unix/sync.c'
    for function in ('NtAlertThreadByThreadId', 'NtWaitForAlertByThreadId'):
        original = _function(read(name).replace("NTSTATUS WINAPI "+function+"(", "static NTSTATUS WINAPI "+function+"("), function).removeprefix("static ")
        renamed = original.replace('NTSTATUS WINAPI '+function, 'static NTSTATUS WINAPI fex_short_'+function, 1)
        if function == 'NtAlertThreadByThreadId':
            wrapper = '''
extern void wine_nx_fex_short_alert(unsigned target, unsigned caller, unsigned result);
NTSTATUS WINAPI NtAlertThreadByThreadId(HANDLE tid)
{
    NTSTATUS result = fex_short_NtAlertThreadByThreadId(tid);
    int saved_errno = errno;
    wine_nx_fex_short_alert(HandleToULong(tid), HandleToULong(NtCurrentTeb()->ClientId.UniqueThread), result);
    errno = saved_errno;
    return result;
}
'''
        else:
            wrapper = '''
extern uint64_t wine_nx_fex_short_wait_begin(unsigned tid);
extern void wine_nx_fex_short_wait_end(unsigned tid, uint64_t begin, uint64_t object, unsigned result);
NTSTATUS WINAPI NtWaitForAlertByThreadId(const void *address, const LARGE_INTEGER *timeout)
{
    unsigned tid = HandleToULong(NtCurrentTeb()->ClientId.UniqueThread);
    int incoming_errno = errno;
    uint64_t begin = wine_nx_fex_short_wait_begin(tid);
    errno = incoming_errno;
    NTSTATUS result = fex_short_NtWaitForAlertByThreadId(address, timeout);
    int saved_errno = errno;
    wine_nx_fex_short_wait_end(tid, begin, (uintptr_t)address, result);
    errno = saved_errno;
    return result;
}
'''
        replace(name, original, renamed+'\n'+wrapper)
