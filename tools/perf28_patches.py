"""PERF27 runtime plus one-shot fault evidence outside exception context."""
import perf27_patches
from perf17_patches import once

adapt_profile = perf27_patches.adapt_profile

def patch_unix(text, project):
    text = once(text, 'static NTSTATUS run_guest( void *args )',
        '#include "' + str(project/'src/runtime/pes13_perf28_unix.h') + '"\n\nstatic NTSTATUS run_guest( void *args )')
    return once(text,
        '        if (status == STATUS_ACCESS_VIOLATION) wine_nx_box64_last_fault( &p->fault_address, &p->fault_access );',
        '        if (status == STATUS_ACCESS_VIOLATION) wine_nx_box64_last_fault( &p->fault_address, &p->fault_access );\n'
        '#ifdef __SWITCH__\n        pes28_after_run(status, p);\n#endif')

def adapt_recipe(text):
    text = perf27_patches.adapt_recipe(text).replace('local/perf27', 'local/perf28')
    text = once(text, 'originals = {',
        'unix_source = source / "source/wow64_box64_unix.c"\noriginals = {')
    text = once(text, 'horizon_source, thunks_source,', 'horizon_source, thunks_source, unix_source,')
    return once(text, '    runtime_source.write_text(runtime_text)',
        '    runtime_source.write_text(runtime_text)\n'
        '    from perf28_patches import patch_unix\n'
        '    unix_text = patch_unix(originals[unix_source].decode(), project)\n'
        '    (project/"local/perf28/wow64_box64_unix.c").write_text(unix_text)\n'
        '    unix_source.write_text(unix_text)')

def adapt(cmake, dynarec, runtime, project):
    # Preserve all historical generated files; rebind only this build's outputs.
    path = project/'tools/perf27_patches.py'
    ns = {'__file__': str(path), '__name__': 'perf28_base'}
    exec(compile(path.read_text().replace("'local/perf27'", "'local/perf28'"), str(path), 'exec'), ns)
    cmake, dynarec, runtime = ns['adapt'](cmake, dynarec, runtime, project)
    dynarec += '\nint wine_nx_perf28_identity(void) { return pes17_check_image(); }\n'
    runtime = once(runtime, 'wine-nx-runtime: generic Wine ntdll PE loader path',
        'PES13-NX: custom Horizon runtime (Wine / Box64 / DXVK / Mesa NVK)')
    return cmake, dynarec, runtime
