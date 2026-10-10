"""LW6: let renamed PES patch settings resolve to the launcher's real preset."""
import shutil
from fextendo_low_window import ROOT, exact


def apply(source, feature):
    runtime = source/'wine-nx-probe/source/runtime.c'
    text = exact(runtime.read_text(), '#define FX_APP_VERSION "0.3.9-lw5"',
                 '#define FX_APP_VERSION "0.3.9-lw6"')
    runtime.write_text(text)
    native = source/'dlls/ntdll/unix'
    file = native/'file.c'
    text = file.read_text()
    anchor = '/******************************************************************************\n *           nt_to_unix_file_name_no_root\n */'
    text = exact(text, anchor, '#ifdef __SWITCH__\n#include "pes_settings_route.h"\n#endif\n\n'+anchor)
    anchor = '''    BOOLEAN is_unix = FALSE;

    name     = attr->ObjectName->Buffer;'''
    text = exact(text, anchor, '''    BOOLEAN is_unix = FALSE;

#ifdef __SWITCH__
    if ((status = pes_settings_route(attr, nt_name))) return status;
#endif
    name     = attr->ObjectName->Buffer;''')
    file.write_text(text)
    shutil.copy2(ROOT/'src/runtime/pes_settings_route.h', native/'pes_settings_route.h')
