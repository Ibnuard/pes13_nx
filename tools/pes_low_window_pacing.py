"""LW2: explicit settings timing policy and Debug-only bounded evidence.

Applied after low-window v1. Memory ownership, FEX, renderer, scheduler, clock
and limiter behavior stay byte/source-identical to that tested integration.
"""
import shutil
from fextendo_low_window import ROOT, exact


def apply(source, feature):
    runtime = source/'wine-nx-probe/source/runtime.c'
    text = runtime.read_text()
    begin = text.index('#ifndef FEXTENDO_PRESETS_H')
    end = text.index('\n#endif', begin) + len('\n#endif')
    assert 'data[i][14]|=1;' in text[begin:end]
    header = (ROOT/'src/runtime/fextendo_presets.h').read_text().strip()
    # Leading license comment is optional in the inlined baseline.
    header = header[header.index('#ifndef FEXTENDO_PRESETS_H'):]
    text = text[:begin] + header + text[end:]
    text = exact(text, '#define FX_APP_VERSION "0.3.9-lw1"',
                 '#define FX_APP_VERSION "0.3.9-lw2"')
    launcher = (ROOT/'src/runtime/fextendo_launcher.h').read_text()
    begin = launcher.index('        if(ready&&wine_nx_launch_debug_active())for(unsigned i=0;i<3;i++){')
    end = launcher.index('\n        }', begin) + len('\n        }')
    anchor = '        log_line("[STARTUP] game settings ready=%d",ready);'
    text = exact(text, anchor, anchor+'\n'+launcher[begin:end])
    text = exact(text,
        '    fex_game_timing_enabled = !guest_tests &&\n'
        '        wine_nx_config_file_bool(RUNTIME_DIR "/fex-game-timing.txt", 0);',
        '    __atomic_store_n(&fex_game_timing_enabled, !guest_tests && wine_nx_launch_debug_active(), __ATOMIC_RELEASE);')
    text = exact(text, '    if (!fex_game_timing_enabled) return;',
                 '    if (!__atomic_load_n(&fex_game_timing_enabled, __ATOMIC_ACQUIRE)) return;')
    text = exact(text, '[FEX3-GAME] enabled=%d; read-only 5s snapshots, periodic log batching',
                 '[FEX3-GAME] enabled=%d; LW2 Debug-only 5s read-only guest settings/timing; no speed scaling')
    anchor = 'static void *log_flusher( void *arg )'
    text = exact(text, anchor, (ROOT/'src/runtime/pes_low_window_diagnostics.h').read_text()+'\n'+anchor)
    text = exact(text, '        fx_production_maintenance_tick(++ticks);',
                 '        fx_production_maintenance_tick(++ticks);\n        fx_low_window_diagnostics(ticks);')
    runtime.write_text(text)
    for name in ('fextendo_presets.h', 'pes_low_window_diagnostics.h'):
        shutil.copy2(ROOT/'src/runtime'/name, feature/name)
