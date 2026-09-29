"""Observe persistent late frames and expose a bounded upstream disk-cache trial."""
import re
from fex_cache_patches import _ENTRY


def apply(read, replace, project):
    name = 'wine-nx-probe/source/runtime.c'
    replace(name, 'static struct fex_frame_hist fex_frame_stats[4];',
            (project/'src/runtime/fex_gap_probe.h').read_text()+'\nstatic struct fex_frame_hist fex_frame_stats[4];')
    replace(name, '        last_begin = last_gap_us = 0;\n        return;',
            '        last_begin = last_gap_us = 0;\n        fex_gap_present(queue, swapchain, 0);\n        return;')
    replace(name, '    __atomic_store_n(&fex_frame_last, end, __ATOMIC_RELAXED);',
            '    __atomic_store_n(&fex_frame_last, end, __ATOMIC_RELAXED);\n'
            '    fex_gap_present(queue, swapchain, 1);')
    replace(name, '    fex_frame_add(&fex_pipeline_stats[stage], armTicksToNs(end - begin) / 1000);',
            '    fex_frame_add(&fex_pipeline_stats[stage], armTicksToNs(end - begin) / 1000);\n'
            '    fex_gap_pipeline_note(stage, armTicksToNs(end - begin) / 1000);')
    replace(name, '        if (ticks % 50 == 0) { fex_sync_report(); fex_jitlog_report(); fex_yield_report(); }',
            '        if (ticks % 50 == 0) { fex_sync_report(); fex_jitlog_report(); fex_yield_report(); fex_gap_report(); }')
    replace(name, '    wine_nx_fex_yield_backoff = wine_nx_config_file_bool(RUNTIME_DIR "/fex_yield_backoff", 1);',
            '    fex_gap_probe_enabled = wine_nx_config_file_bool(RUNTIME_DIR "/fex_gap_probe", 1);\n'
            '    log_line("[FEX3-GAP] v1 enabled=%d threshold_us=50000 capacity=32; one thread tick query per Present", fex_gap_probe_enabled);\n'
            '    wine_nx_fex_yield_backoff = wine_nx_config_file_bool(RUNTIME_DIR "/fex_yield_backoff", 1);')
    # Keep FEX's configuration/feature hash buckets below this parent directory.
    # Do not use DiskCachePath, which bypasses that automatic partitioning.
    extra = [r'FEX_APP_CACHE_LOCATION=C:\\fex-jit-cache\\\0',
             r'FEX_DISKCACHEFILEMAPPING=0\0', r'FEX_DISKCACHEANONCACHING=0\0',
             r'FEX_DISKCACHEMEMORYSIZE=0\0', r'FEX_DISKCACHEMAXFILESIZE=67108864\0']
    for symbol in ('runtime_environment', 'fex_jit_large_environment', 'fex_jit_small_environment'):
        pattern = re.compile(r'static const char '+symbol+r'\[\] =\n(?:    "(?:[^"\\\n]|\\.)*"(?:\n|;\n))+')
        match = pattern.search(read(name))
        if not match: raise ValueError('Missing environment '+symbol)
        entries = _ENTRY.findall(match.group())
        if any(e.startswith('FEX_DISKCACHE=') for e in entries): raise ValueError('Duplicate cache option')
        def block(label, additions):
            items = sorted(entries + additions, key=lambda e:e.split('=')[0].lower())
            return 'static const char '+label+'[] =\n'+'\n'.join('    "'+e+'"' for e in items)+';\n'
        replace(name, match.group(), block(symbol, [r'FEX_DISKCACHE=0\0'])+'\n'+
                block(symbol+'_disk', extra+[r'FEX_DISKCACHE=1\0']))
    anchor = '        log_line("[PES13-GFX] DXVK Vulkan; WineD3D CSMT override inactive");'
    replace(name, anchor,
            '        const int disk_cache = wine_nx_config_file_bool(RUNTIME_DIR "/fex_diskcache", 0);\n'
            '        if (disk_cache) {\n'
            '            const int large = environment == fex_jit_large_environment;\n'
            '            const int small = environment == fex_jit_small_environment;\n'
            '            environment = large ? fex_jit_large_environment_disk : small ? fex_jit_small_environment_disk : runtime_environment_disk;\n'
            '            environment_bytes = large ? sizeof(fex_jit_large_environment_disk) : small ? sizeof(fex_jit_small_environment_disk) : sizeof(runtime_environment_disk);\n'
            '        }\n'
            '        log_line("[FEX3-DISKCACHE] requested=%d mapping=0 anonymous=0 memory_lru=0 main_file_limit_mb=64; actual cache use unverified", disk_cache);\n'+anchor)
    replace(name, '"pes13-fex3-stable-balance"', '"pes13-fex3-gap-audit"')
