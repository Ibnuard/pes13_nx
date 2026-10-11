"""Bind startup checks to the frozen original r6 launcher, without Kitserver changes."""
from pathlib import Path
import re
from fextendo_low_window import ROOT, exact

FILES=('fextendo_runtime_api.h','fextendo_runtime_module.c','fextendo_runtime_fixer.h',
       'fextendo_runtime_download.h','fextendo_runtime_catalog.h','fextendo_install_check.h',
       'fextendo_startup_check.h','fextendo_startup_switch.h','fextendo_startup_heap.h')

def replace_header(data,guard,path):
    start=data.index('/* LGPL-2.1-or-later.',data.index('#ifndef '+guard)-250)
    guard_at=data.index('#ifndef '+guard,start)
    depth=0;end=None
    for m in re.finditer(r'^\s*#\s*(if|ifdef|ifndef|endif)\b[^\n]*\n?',data[guard_at:],re.M):
        if m.group(1)=='endif':
            depth-=1
            if depth==0:end=guard_at+m.end();break
        else:depth+=1
    assert end is not None,guard
    return data[:start]+path.read_text()+data[end:]

def apply(source,feature):
    import shutil
    for n in FILES:shutil.copy2(ROOT/'src/runtime'/n,feature/n)
    runtime=source/'wine-nx-probe/source/runtime.c'
    data=runtime.read_text()
    for guard,name in [('FEXTENDO_UI_H','fextendo_ui.h'),('FEXTENDO_LAUNCHER_H','fextendo_launcher.h')]:
        data=replace_header(data,guard,ROOT/'src/runtime'/name)
    data=exact(data,'    if (!fx_launch_memory_validate()) return 0;','    fx_launch_memory_read(); /* Startup checker owns admission before Wine. */')
    data=exact(data,'    if (guest_tests) { consoleInit(NULL); wine_nx_console_active = 1; }',
        '    if (guest_tests) { if (!fx_launch_memory_validate()) return 0; consoleInit(NULL); wine_nx_console_active = 1; }')
    runtime.write_text(data)
    cmake=source/'wine-nx-probe/CMakeLists.txt'
    cmake.write_text(cmake.read_text()+'\n'
        'target_link_libraries(wine-nx-runtime PRIVATE curl minizip z nx)\n'
        'add_library(fextendo-repair OBJECT "'+str(feature/'fextendo_runtime_module.c')+'")\n'
        'target_compile_definitions(fextendo-repair PRIVATE __SWITCH__)\n'
        'target_compile_options(fextendo-repair PRIVATE -ffunction-sections -fdata-sections)\n'
        'target_sources(wine-nx-runtime PRIVATE $<TARGET_OBJECTS:fextendo-repair>)\n')
