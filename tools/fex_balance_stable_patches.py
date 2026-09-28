"""Keep proven yield-burst pacing; replace global reshuffles with one useful move."""


def apply(read, replace, project):
    name = 'wine-nx-probe/source/thread_profile.c'
    replace(name, '#include "thread_profile.h"',
            '#include "thread_profile.h"\n#include "' + str(project/'src/runtime/fex_balance_stable.h') + '"')
    replace(name, 'int wine_nx_balance_enabled = 1;',
            'int wine_nx_balance_enabled = 1;\nint wine_nx_fex_balance_stable = 1;')
    replace(name, '    after = nx_balance_assign( balance, count, cores, &before );\n'
                  '    if (!urgent && after + 5 * NX_BALANCE_SLACK / 3 >= before)',
            '    after = wine_nx_fex_balance_stable\n'
            '        ? fex_balance_stable( balance, count, cores, &before )\n'
            '        : nx_balance_assign( balance, count, cores, &before );\n'
            '    if (wine_nx_fex_balance_stable ? !fex_balance_has_move( balance, count )\n'
            '                                   : (!urgent && after + 5 * NX_BALANCE_SLACK / 3 >= before))')
    anchor = '    pthread_mutex_unlock( &registry_mutex );\n    wine_nx_runtime_trace( line );\n}'
    replace(name, anchor,
            '    pthread_mutex_unlock( &registry_mutex );\n'
            '    if (wine_nx_fex_balance_stable)\n'
            '        len = appendf( line, len, "; policy=single tick=%llu cost_us=%llu",\n'
            '                       (unsigned long long)now,\n'
            '                       (unsigned long long)armTicksToNs( armGetSystemTick() - now ) / 1000 );\n'
            '    wine_nx_runtime_trace( line );\n}')
    name = 'wine-nx-probe/source/runtime.c'
    replace(name, 'static int log_flusher_running;',
            'extern int wine_nx_fex_balance_stable;\nstatic int log_flusher_running;')
    anchor = '    if (wine_nx_config_file_bool(RUNTIME_DIR "/no-balance.txt", 0)) wine_nx_balance_enabled = 0;'
    replace(name, anchor,
            '    wine_nx_fex_balance_stable = wine_nx_config_file_bool(RUNTIME_DIR "/fex_balance_stable", 1);\n'
            '    log_line("[FEX3-BALANCE] v1 stable=%d max_moves=1 pair_gain_gt_permille=50; projected registered loads only",\n'
            '             wine_nx_fex_balance_stable);\n'+anchor)
    replace(name, '"pes13-fex3-yield-burst"', '"pes13-fex3-stable-balance"')
