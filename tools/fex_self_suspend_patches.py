"""Real synchronous self-suspension in the isolated FEX Horizon server."""


def apply(read, replace, project):
    name = 'dlls/ntdll/unix/horizon_threads.h'
    replace(name, '    int suspend;     /* start-gate count; a running thread is never suspended */',
            '    int suspend;     /* start gate or a synchronous self-suspend count */\n'
            '    int self_suspended; /* guest is held in its suspend RPC until count reaches zero */')
    name = 'dlls/ntdll/unix/horizon.c'
    data = read(name)
    first = data.index('static int horizon_server_handle_suspend_thread(')
    last = data.index('static int horizon_server_handle_terminate_thread(', first)
    replace(name, data[first:last], (project / 'src/runtime/fex_self_suspend.h').read_text() + '\n')
    name = 'wine-nx-probe/source/thread_profile.c'
    replace(name, 'extern void wine_nx_fex_suspend_report(void);',
            'extern void wine_nx_fex_suspend_report(void);\n'
            'extern void wine_nx_fex_self_suspend_report(void);')
    replace(name, '    wine_nx_fex_suspend_report();',
            '    wine_nx_fex_suspend_report();\n    wine_nx_fex_self_suspend_report();')
