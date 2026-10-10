"""LW4: isolate the optional Gameplaytool parent through Wine load policy."""
import shutil
from fextendo_low_window import ROOT, exact


def apply(source, feature):
    runtime=source/'wine-nx-probe/source/runtime.c'
    text=runtime.read_text()
    text=exact(text,'#define FX_APP_VERSION "0.3.9-lw3"','#define FX_APP_VERSION "0.3.9-lw4"')
    text=exact(text,'int main( int argc, char **argv )',
               (ROOT/'src/runtime/pes_gameplaytool_control.h').read_text()+'\nint main( int argc, char **argv )')
    anchor='    const int guest_tests = wine_nx_config_file_bool(RUNTIME_DIR "/run-guest-tests.txt", 0);'
    text=exact(text,anchor,anchor+'''
    const int gameplaytool_enabled = wine_nx_config_file_bool(RUNTIME_DIR "/kitserver_gameplaytool", 0);
    if (!pes_gameplaytool_control(guest_tests, gameplaytool_enabled))
    {
        log_line("[LW4-KITCONTROL] failed to set optional DLL policy; launch stopped");
        park_forever();
    }
''')
    # Report only after the launcher has selected normal / Debug launch.
    # Earlier log calls are intentionally suppressed by the production gate.
    text=exact(text,'    fxt_low_window_report();','''    fxt_low_window_report();
    log_line("[LW4-KITCONTROL] Gameplaytool=%s; guest_tests=%d; Wine load policy only; no game clock scaling",
             guest_tests ? "guest-test unchanged" : gameplaytool_enabled ? "original" : "disabled", guest_tests);''')
    runtime.write_text(text)
    shutil.copy2(ROOT/'src/runtime/pes_gameplaytool_control.h',feature/'pes_gameplaytool_control.h')
