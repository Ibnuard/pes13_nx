"""Isolated PES 39-bit/low-window integration over the frozen Kit15 native tree.

Guest VA mappings keep Wine's existing backing ownership/commit machinery.
Native libnx aliases use the upper 39-bit domain from its first initialization.
"""
from pathlib import Path
import shutil
from fextendo_low_window import ROOT, SOURCE, exact


def apply(source, feature):
    changed = []
    def edit(path, old, new):
        path.write_text(exact(path.read_text(), old, new))
        changed.append(str(path))
    native = source / 'wine-nx-probe/source'
    for name in ('pes_low_window.c', 'pes_low_window.h'):
        shutil.copy2(SOURCE / name, native / name)
        changed.append(str(native / name))
    # Header shared by the runtime's copied feature includes and libnx manager.
    shutil.copy2(SOURCE / 'pes_low_window.h', feature / 'pes_low_window.h')
    launch = feature / 'fextendo_launch_memory.h'
    edit(launch, '#include <stdio.h>', '#include <stdio.h>\n#include "pes_low_window.h"')
    edit(launch, 'return fx_memory_mode(&fx_startup_memory)==FX_MEMORY_32_NO_ALIAS;',
         'return fx_memory_mode(&fx_startup_memory)==FX_MEMORY_39 &&\n'
         '        fxt_low_window_layout(fx_startup_memory.base,fx_startup_memory.size);')
    edit(launch, 'int mode=fx_memory_mode(m);if(mode==FX_MEMORY_32_NO_ALIAS)return 1;',
         'int mode=fx_memory_mode(m);\n'
         '    if(wine_nx_launch_memory_compatible() && fxt_low_window_preflight())return 1;')
    edit(launch, 'FEXTendo requires 32-bit no-alias.', 'This experimental build requires verified 39-bit low-window.')
    edit(launch, 'Open PES13 using the supplied FEXTendo NSP on the HOME Menu.',
         'Open the PES13 Low Window HOME tile using the FEXTendo Memory v1 TEST boot entry.')
    edit(launch, 'Install the FEXTendo NSP from github.com/Ibnuard/pes13_nx/releases.',
         'Use the separate experimental low-window NSP and the tested v1 kernel/loader pair.')
    edit(launch, 'Query results: %x / %x / %x / %x",',
         'Query results: %x / %x / %x / %x\\nPreflight: %s",')
    edit(launch, 'm->base_rc,m->size_rc,m->alias_rc,m->total_rc);',
         'm->base_rc,m->size_rc,m->alias_rc,m->total_rc,fxt_low_window_error());')
    vm = feature / 'fextendo_virtmem.c'
    edit(vm, '#include <stdint.h>', '#include <stdint.h>\n#include "pes_low_window.h"')
    edit(vm, '\n}\n\nvoid virtmemLock(void)', '''
    /* The opt-in kernel exposes low guest VA to Wine. Native libnx address
     * selection excludes it from the FIRST use, before applet initialization.
     * Fixed Wine mappings retain their own reservations and backing lifetime. */
    if (fxt_low_window_layout(g_AslrRegion.start,g_AslrRegion.end-g_AslrRegion.start)) {
        g_AslrRegion.start=FXT_NATIVE_BASE;
        if (g_StackRegion.start<FXT_NATIVE_BASE) g_StackRegion.start=FXT_NATIVE_BASE;
    }
}

void virtmemLock(void)''')
    runtime = native / 'runtime.c'
    edit(runtime, '#define FX_APP_VERSION "0.3.9-kit15"', '#define FX_APP_VERSION "0.3.9-lw1"')
    edit(runtime, '    const unsigned fex_profile = pes13_fex_select_performance_profile(guest_tests,',
         '    fxt_low_window_report();\n    const unsigned fex_profile = pes13_fex_select_performance_profile(guest_tests,')
    cmake = source / 'wine-nx-probe/CMakeLists.txt'
    cmake.write_text(cmake.read_text() + '\ntarget_sources(wine-nx-runtime PRIVATE source/pes_low_window.c)\n')
    changed.append(str(cmake))
    return sorted(set(changed))
