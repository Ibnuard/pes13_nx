"""LW5: retain NT failures and inspect queued Kitserver pipe data in Debug launch."""
import shutil
from fextendo_low_window import ROOT, exact
from pes_low_window_live import apply_wait_attribution


def apply(source, feature):
    runtime = source/'wine-nx-probe/source/runtime.c'
    text = runtime.read_text()
    text = exact(text, '#define FX_APP_VERSION "0.3.9-lw4"', '#define FX_APP_VERSION "0.3.9-lw5"')
    text = exact(text, '#include "fextendo_wait_probe.h"',
                 '#include "fextendo_wait_probe.h"\nextern void wine_nx_asset_pipe_report(void);')
    text = exact(text, 'if(ticks%25==0)fx_wait_probe_tick();',
                 'if(ticks%25==0){fx_wait_probe_tick();if(wine_nx_launch_debug_active())wine_nx_asset_pipe_report();}')
    text = exact(text, '    fxt_low_window_report();', '''    fxt_low_window_report();
    log_line("[LW5-ASSET] Debug-only retained NT failures and bounded pipe snapshots; no I/O behavior changes");''')
    runtime.write_text(text)
    # The native base header intentionally has no PES Vulkan observer. LW3
    # added that hook to its generated copy; preserve it when adding LW5.
    wait_text=apply_wait_attribution((ROOT/'src/runtime/fextendo_wait_probe.h').read_text())
    (feature/'fextendo_wait_probe.h').write_text(wait_text)
    native = source/'dlls/ntdll/unix'
    horizon = native/'horizon.c'
    text = exact(horizon.read_text(), '#include "horizon_anon_pipe_server.h"',
                 '#include "horizon_anon_pipe_server.h"\n#include "horizon_asset_probe.h"')
    horizon.write_text(text)
    shutil.copy2(ROOT/'src/runtime/horizon_asset_probe.h', native/'horizon_asset_probe.h')
