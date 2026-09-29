"""Reduce polling bookkeeping; keep original Wine delay/QPC and OFF control."""


def apply(read, replace, project):
    name = 'dlls/ntdll/unix/signal_arm64.c'
    anchor = 'unsigned int wine_nx_syscall_counts[0x2000];'
    replace(name, anchor, anchor + '\n#include "' + str(project/'src/runtime/fex_polling_counters.h') + '"')
    old = '''        __atomic_add_fetch( &wine_nx_syscalls, 1, __ATOMIC_RELAXED );
        __atomic_add_fetch( &wine_nx_syscall_counts[syscall_id & 0x1fff], 1, __ATOMIC_RELAXED );'''
    replace(name, old, '''        /* Match both the pinned ID and actual handler. Unknown mappings
         * retain the original path, including full diagnostics in control. */
        if (!(((syscall_id == 0x31 && (void *)handler == (void *)NtQueryPerformanceCounter) ||
               (syscall_id == 0x34 && (void *)handler == (void *)NtDelayExecution)) &&
              fex_poll_count(syscall_id)))
        {
''' + old + '\n        }')

    name = 'dlls/ntdll/unix/sync.c'
    anchor = 'extern void wine_nx_fex_yield_pause_note(unsigned, uint64_t);'
    replace(name, anchor, anchor + '\n#include "' + str(project/'src/runtime/fex_polling_yield.h') + '"')
    anchor = 'NTSTATUS WINAPI NtYieldExecution(void)\n{\n#ifdef __SWITCH__'
    replace(name, anchor, anchor + '\n    if (wine_nx_fex_polling) return fex_poll_yield(NULL);')
    anchor = '    const int64_t requested = timeout ? timeout->QuadPart : 0;'
    replace(name, anchor, anchor + '''
    if (wine_nx_fex_polling && !alertable && timeout && !requested) {
        uint64_t elapsed;
        NTSTATUS result = fex_poll_yield(&elapsed);
        TEB *teb = NtCurrentTeb();
        if (teb) wine_nx_fex_delay_zero_note((unsigned)(ULONG_PTR)teb->ClientId.UniqueThread, elapsed);
        return result;
    }''')

    name = 'wine-nx-probe/source/runtime.c'
    replace(name, 'void wine_nx_fex_delay_note(unsigned tid, int alertable, int has_timeout,\n'
                  '                          int64_t timeout, uint64_t begin, int status)\n'
                  '{\n    uint64_t elapsed = armTicksToNs(armGetSystemTick() - begin) / 1000;',
                  'static void fex_delay_note_elapsed(unsigned tid, int alertable, int has_timeout,\n'
                  '                                   int64_t timeout, uint64_t elapsed, int status)\n{')
    anchor = 'static void fex_sync_report(void)'
    replace(name, anchor, '''void wine_nx_fex_delay_note(unsigned tid, int alertable, int has_timeout,
                          int64_t timeout, uint64_t begin, int status)
{
    uint64_t elapsed = armTicksToNs(armGetSystemTick() - begin) / 1000;
    fex_delay_note_elapsed(tid, alertable, has_timeout, timeout, elapsed, status);
}

void wine_nx_fex_delay_zero_note(unsigned tid, uint64_t elapsed_us)
{
    fex_delay_note_elapsed(tid, 0, 1, 0, elapsed_us, 0);
}

''' + anchor)
    anchor = '    const int fex_dxvk_balance = wine_nx_config_file_bool(RUNTIME_DIR "/fex_dxvk_balance", 1);'
    replace(name, anchor, '''    extern int wine_nx_fex_polling;
    wine_nx_fex_polling = !guest_tests && wine_nx_config_file_bool(RUNTIME_DIR "/fex_polling", 1);
    log_line("[FEX3-POLL] v1 enabled=%d counters=256 retained per-thread slots; yield shares 100ns monotonic samples; no clock scaling", wine_nx_fex_polling);
''' + anchor)
    anchor = '        if (++calls % 2) return;'
    replace(name, anchor, anchor + '''
        extern void wine_nx_fex_poll_totals(unsigned out[2]);
        unsigned poll_counts[2];
        wine_nx_fex_poll_totals(poll_counts);
        syscalls += poll_counts[0] + poll_counts[1];''')
    anchor = '                unsigned int count = __atomic_load_n( &wine_nx_syscall_counts[id], __ATOMIC_RELAXED );'
    replace(name, anchor, anchor + '\n                if (id == 0x31) count += poll_counts[0];\n                if (id == 0x34) count += poll_counts[1];')
    replace(name, '"pes13-fextendo-cpu-balance-v2"', '"pes13-fextendo-polling-v1"')
