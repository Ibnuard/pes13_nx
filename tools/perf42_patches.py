"""Optional, exact startup lookup recovery on the hardware-tested PERF40 base."""
from pathlib import Path

from perf17_patches import once
import perf40_patches

adapt_profile = perf40_patches.adapt_profile


def base40(project):
    path = project / 'tools/perf40_patches.py'
    source = path.read_text()
    for old, new in (
        ('local/perf40', 'local/perf42'),
        ('runtime-perf40-early-round', 'runtime-perf42-startup-guard'),
        ('pes13-nx-0.2.0-perf40-early-round', 'pes13-nx-0.2.0-perf42-startup-guard'),
        ('PES13-NX PERF40 EARLYROUND', 'PES13-NX PERF42 BOOTGUARD'),
    ):
        source = source.replace(old, new)
    namespace = {'__file__': str(path), '__name__': 'perf42_base40'}
    exec(compile(source, str(path), 'exec'), namespace)
    return namespace


def patch_unix(source, project):
    source = once(source, 'static NTSTATUS run_guest( void *args )',
                  '#include "' + str(project / 'src/runtime/pes13_perf42_unix.h') + '"\n\n'
                  'static NTSTATUS run_guest( void *args )')
    fault = '''        if (status == STATUS_ACCESS_VIOLATION) wine_nx_box64_last_fault( &p->fault_address, &p->fault_access );'''
    source = once(source, fault, fault + '''
#ifdef __SWITCH__
        if (pes42_after_run( status, p ))
        {
            p->fault_address = p->fault_access = 0;
            status = STATUS_TIMEOUT;
        }
#endif
''')
    return source


def adapt(cmake, dynarec, runtime, project):
    cmake, dynarec, runtime = base40(project)['adapt'](
        cmake, dynarec, runtime, project)
    dynarec = 'static int pes42_mode;\n' + dynarec
    dynarec = once(dynarec, '    apply_box64_options();',
                   '    apply_box64_options();\n'
                   '    pes42_mode = wine_nx_config_file_bool(\n'
                   '        "sdmc:/switch/pes13-nx/perf42-startup-guard.txt", 1);')
    dynarec += '''
int wine_nx_perf42_guard_enabled(void) { return pes42_mode; }
int wine_nx_perf42_identity(void) { return pes17_check_image(); }
'''
    return cmake, dynarec, runtime


def adapt_recipe(source):
    source = base40(Path(__file__).resolve().parents[1])['adapt_recipe'](source)
    source = once(source, 'originals = {',
                  'unix_source = source / "source/wow64_box64_unix.c"\noriginals = {')
    source = once(source, 'vulkan_source, runtime_source, horizon_source,',
                  'vulkan_source, runtime_source, horizon_source, unix_source,')
    return once(source, '    runtime_source.write_text(runtime_text)',
                '    runtime_source.write_text(runtime_text)\n'
                '    from perf42_patches import patch_unix\n'
                '    unix_text = patch_unix(originals[unix_source].decode(), project)\n'
                '    (project / "local/perf42/wow64_box64_unix.c").write_text(unix_text)\n'
                '    unix_source.write_text(unix_text)')
