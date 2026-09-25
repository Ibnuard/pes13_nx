"""FEX team-selection observations, bounded and separate from continuous profiling."""


def apply(read, replace, project):
    name = 'dlls/ntdll/unix/horizon.c'
    anchor = 'static int horizon_server_handle_suspend_thread( struct horizon_server_connection *connection,'
    replace(name, anchor, (project / 'src/runtime/fex_suspend_observe.h').read_text() + '\n' + anchor)
    replace(name, '        status = horizon_thread_suspend( &object->thread, &reply.count );\n'
                  '        tid = object->thread.tid;',
            '        status = horizon_thread_suspend( &object->thread, &reply.count );\n'
            '        tid = object->thread.tid;\n'
            '        fex_suspend_observe(connection->tid, tid, status, object->thread.started, object->thread.terminated);')

    name = 'wine-nx-probe/source/thread_profile.c'
    replace(name, 'static pthread_mutex_t registry_mutex = PTHREAD_MUTEX_INITIALIZER;',
            'static void wine_nx_fex_stall_remove(Handle handle);\n'
            'static void wine_nx_fex_stall_targets(const struct nx_prof_row *rows, unsigned count);\n'
            'extern void wine_nx_fex_suspend_report(void);\n\n'
            'static pthread_mutex_t registry_mutex = PTHREAD_MUTEX_INITIALIZER;')
    replace(name, '        if (targets[i].handle == handle) targets[i].handle = 0;\n'
                  '    pthread_mutex_unlock( &profile_mutex );',
            '        if (targets[i].handle == handle) targets[i].handle = 0;\n'
            '    wine_nx_fex_stall_remove(handle);\n'
            '    pthread_mutex_unlock( &profile_mutex );')
    replace(name, '    server_report();\n    if (profiling) profile_report( rows, count );',
            '    server_report();\n'
            '    wine_nx_fex_suspend_report();\n'
            '    wine_nx_fex_stall_targets(rows, count);\n'
            '    if (profiling) profile_report( rows, count );')
    anchor = read(name)
    replace(name, anchor, anchor + '\n' + (project / 'src/runtime/fex_stall_probe.h').read_text())

    name = 'wine-nx-probe/source/runtime.c'
    replace(name, '        runtime_tick_std_streams();\n'
                  '        if ((!wine_nx_production && ticks % 25 == 0) ||',
            '        if (ticks % 25 == 0)\n'
            '        {\n'
            '            extern unsigned int wine_nx_vk_presents __attribute__((weak));\n'
            '            extern void wine_nx_fex_stall_probe(unsigned presents, unsigned seconds);\n'
            '            if (&wine_nx_vk_presents) wine_nx_fex_stall_probe(\n'
            '                __atomic_load_n(&wine_nx_vk_presents, __ATOMIC_RELAXED), ticks / 5);\n'
            '        }\n'
            '        runtime_tick_std_streams();\n'
            '        if ((!wine_nx_production && ticks % 25 == 0) ||')
