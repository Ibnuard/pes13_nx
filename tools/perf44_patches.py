"""PERF42 game policy plus bounded CPU-side Vulkan stage measurements."""
from pathlib import Path

from perf17_patches import once
import perf27_patches


def base42(project):
    path = project / 'tools/perf42_patches.py'
    source = path.read_text()
    for old, new in (
        ('local/perf42', 'local/perf44'),
        ('runtime-perf42-startup-guard', 'runtime-perf44-event-pipeline'),
        ('pes13-nx-0.2.0-perf42-startup-guard', 'pes13-nx-0.2.0-perf44-event-pipeline'),
        ('PES13-NX PERF42 BOOTGUARD', 'PES13-NX PERF44 PIPELINE'),
    ):
        assert old in source, old
        source = source.replace(old, new)
    namespace = {'__file__': str(path), '__name__': 'perf44_base42'}
    exec(compile(source, str(path), 'exec'), namespace)
    return namespace


def _rename_spans(source, project):
    return (source.replace(str(project / 'src/runtime/pes13_perf27_metrics.h'),
                           str(project / 'src/runtime/pes13_perf44_metrics.h'))
                  .replace('PES27_', 'PES44_')
                  .replace('wine_nx_perf27_span', 'wine_nx_perf44_span')
                  .replace('pes27_present_impl', 'pes44_present_impl')
                  .replace('pes27_after', 'pes44_after'))


def patch_vulkan(source, project):
    result = _rename_spans(perf27_patches.patch_vulkan(source, project), project)
    assert 'PES27_' not in result and 'PES44_TIME(' in result
    return result


def patch_thunks(source, project):
    result = _rename_spans(perf27_patches.patch_thunks(source, project), project)
    assert 'PES27_' not in result and 'PES44_TIME(' in result
    return result


def adapt(cmake, dynarec, runtime, project):
    cmake, dynarec, runtime = base42(project)['adapt'](
        cmake, dynarec, runtime, project)
    runtime = once(runtime, 'static void log_line(const char *fmt, ...);',
        'static void log_line(const char *fmt, ...);\n'
        '#include "' + str(project / 'src/runtime/pes13_perf44_runtime.h') + '"')
    runtime = once(runtime, '    wine_nx_thread_report();',
                   '    pes44_report();\n    wine_nx_thread_report();')
    return cmake, dynarec, runtime


def adapt_recipe(source):
    project = Path(__file__).resolve().parents[1]
    source = base42(project)['adapt_recipe'](source)
    source = once(source, 'originals = {',
        'thunks_source = wine_source / "dlls/winevulkan/vulkan_thunks.c"\n'
        'originals = {')
    source = once(source,
        'vulkan_source, runtime_source, horizon_source, unix_source,',
        'vulkan_source, runtime_source, horizon_source, unix_source, thunks_source,')
    source = once(source, '    vulkan_source.write_text(vulkan_text)',
        '    from perf44_patches import patch_vulkan\n'
        '    vulkan_text = patch_vulkan(vulkan_text, project)\n'
        '    (project / "local/perf44/vulkan.c").write_text(vulkan_text)\n'
        '    vulkan_source.write_text(vulkan_text)')
    source = once(source, '    unix_source.write_text(unix_text)',
        '    unix_source.write_text(unix_text)\n'
        '    from perf44_patches import patch_thunks\n'
        '    thunks_text = patch_thunks(originals[thunks_source].decode(), project)\n'
        '    (project / "local/perf44/vulkan_thunks.c").write_text(thunks_text)\n'
        '    thunks_source.write_text(thunks_text)')
    return source


adapt_profile = base42(Path(__file__).resolve().parents[1])['adapt_profile']
