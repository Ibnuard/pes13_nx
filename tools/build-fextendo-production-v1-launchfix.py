"""Rebuild the archived production v1 sources with only the Wine startup fix.

Does not import the live runtime patch set or the current FEX adapters. The
archive, build inputs and normalized generated-source delta are all checked.
"""
import argparse
import difflib
import json
from pathlib import Path
import struct
import subprocess
import sys

import fextendo_package as p

BASE_SHA = '99bd297a20cb3aaaea867ab43d554dd2b6d55117211c0c3d3b36106e9247de1e'
BASE_COMMIT = 'ab1d9046c820ac13875d31e2347f12913731d6ea'
NAME = 'production-v1-launchfix'
FIX = '''    # Horizon's custom entry does not initialize upstream Wine main_argv.
    # Disable channel setup directly, before the guest or a TEB exists.
    body(debug, 'static void init_options(void)\\n',
         '    nb_debug_options = 0;\\n    default_flags = 0;')
    body(debug, 'unsigned char __cdecl __wine_dbg_get_channel_flags( struct __wine_debug_channel *channel )\\n',
         '    channel->flags = 0;\\n    return 0;')
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-root', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    base, _ = p.verified_zip(p.ROOT / 'dist/pes13-fextendo-production-no-log-v1.zip', BASE_SHA)
    old = json.loads(base['evidence/runtime/runtime-build.json'])
    previous = json.loads(base['evidence/runtime/wine-patches.json'])
    work = p.ROOT / 'local/fex3' / NAME
    project = work / 'project'
    project.mkdir(parents=True, exist_ok=False)
    for name, data in base.items():
        if name.startswith('source/'):
            dest = project / name.removeprefix('source/')
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
    for name, digest in old['patch_sources'].items():
        p.checked(project / name, digest)
    for name, digest in old['adapter_sources'].items():
        p.checked(project / 'src/fex' / name, digest)
    assert {f.name for f in (project / 'src/fex').iterdir() if f.is_file()} == set(old['adapter_sources'])

    # The original bundle omitted shared helpers and headers such as
    # perf34_patches.py and pes13_config.h. Recover only missing files from the
    # commit predating v1; never fall through to live experimental sources.
    recovered = {}
    names = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', BASE_COMMIT,
                                     '--', 'tools', 'src/runtime'], cwd=p.ROOT, text=True).splitlines()
    for name in names:
        dest = project / name
        if dest.exists() or dest.suffix not in ('.py', '.h'):
            continue
        data = subprocess.check_output(['git', 'show', BASE_COMMIT + ':' + name], cwd=p.ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        recovered[name] = p.sha(data)
    blob = base[p.NRO]
    asset = struct.unpack_from('<I', blob, 0x18)[0]
    offset, size = struct.unpack_from('<QQ', blob, asset + 8)
    icon = blob[asset + offset:asset + offset + size]
    assert p.sha(icon) == old['metadata']['icon_sha256']
    icon_path = project / 'assets/fextendo-v3/nro-icon.jpg'
    icon_path.parent.mkdir(parents=True, exist_ok=True)
    icon_path.write_bytes(icon)

    patch = project / 'tools/fextendo_silent_patches.py'
    original = patch.read_text()
    anchor = "    debug = 'dlls/ntdll/unix/debug.c'\n"
    assert original.count(anchor) == 1
    patch.write_text(original.replace(anchor, anchor + FIX))
    (work / 'production-v1-launchfix.patch').write_text(''.join(difflib.unified_diff(
        original.splitlines(True), patch.read_text().splitlines(True),
        fromfile='production-v1/tools/fextendo_silent_patches.py',
        tofile='production-v1-launchfix/tools/fextendo_silent_patches.py')))

    runtime = work / 'runtime'
    payload = runtime / 'payload'
    payload.mkdir(parents=True)
    (runtime / 'runtime-build.json').write_bytes(p.enc(old))
    for name, field in (('ntdll.dll', 'ntdll_sha256'), ('wow64.dll', 'wow64_sha256'),
                        ('fex-stress.exe', 'guest_sha256')):
        src = p.ROOT / 'local/fex3/production-no-log-v1/runtime/payload' / name
        (payload / name).write_bytes(p.checked(src, old[field]))
    command = [sys.executable, str(project / 'tools/build-fex-runtime.py'),
               '--integration', '--native-only', '--build-root', str(args.build_root.resolve()),
               '--output-dir', str(runtime), '--toolchain', old['toolchain_path'], '--jobs', str(args.jobs)]
    flags = ('runtime_fixes', 'stability', 'hang_audit', 'warm_audit', 'jit_latency',
             'sleep_deadline', 'worker_cores', 'jit_log_queue', 'yield_burst', 'yield_adaptive',
             'stable_balance', 'gap_audit', 'launcher', 'memory_audit', 'memory_budget_filter',
             'short_trace', 'dxvk_core3', 'polling', 'fast_api', 'silent_production',
             'diagnostic', 'resume_gate', 'samecore_yield')
    command += ['--' + key.replace('_', '-') for key in flags if old[key]]
    (work / 'build-command.json').write_bytes(p.enc(command))
    print('Building archived production v1 with the startup-only patch', flush=True)
    with (runtime / 'driver.log').open('w') as output:
        result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        print('\n'.join((runtime / 'driver.log').read_text().splitlines()[-65:]))
        result.check_returncode()

    current = p.read(runtime / 'runtime-build.json')
    patches = p.read(runtime / 'wine-patches.json')
    assert current['adapter_sources'] == old['adapter_sources']
    for key in (*flags, 'native_dependencies', 'ntdll_sha256', 'wow64_sha256', 'guest_sha256', 'toolchain_path'):
        assert current[key] == old[key], key
    assert p.delta(old['patch_sources'], current['patch_sources']) == ['tools/fextendo_silent_patches.py']
    wine = Path(current['native_source']).parent.parent
    changed = {}
    # Absolute local include paths change with the archived project directory.
    # Normalize only that path for comparison; every code byte must match v1
    # outside the two repaired functions in debug.c.
    debug_patch = []
    for kind in ('native-source', 'pe-source'):
        assert set(patches[kind]) == set(previous[kind])
        changed[kind] = []
        for name, digest in patches[kind].items():
            data = p.checked(wine / kind / name, digest)
            archived = base['source/generated/wine/' + kind + '/' + name]
            normalized = data.replace(str(project).encode(), str(p.ROOT).encode())
            if normalized != archived:
                changed[kind].append(name)
                debug_patch.extend(difflib.unified_diff(
                    archived.decode().splitlines(True), normalized.decode().splitlines(True),
                    fromfile='production-v1/' + name, tofile=NAME + '/' + name))
            # Freeze the generated inputs actually used, before a later build.
            (project / 'generated/wine' / kind / name).write_bytes(data)
        changed[kind].sort()
    assert changed == {'native-source': ['dlls/ntdll/unix/debug.c'], 'pe-source': []}, changed
    (work / 'generated-startup-fix.patch').write_text(''.join(debug_patch))
    report = {
        'passed': True, 'hardware_tested': False, 'baseline_archive_sha256': BASE_SHA,
        'baseline_nro_sha256': old['nro_sha256'], 'nro_sha256': current['nro_sha256'],
        'native_elf_sha256': current['native_elf_sha256'], 'generated_code_delta': changed,
        'adapters_identical_to_production_v1': True, 'native_dependencies_identical_to_production_v1': True,
        'build_flags_identical_to_production_v1': True, 'pe_payloads_identical_to_production_v1': True,
        'recovered_helpers_commit': BASE_COMMIT, 'recovered_helpers': recovered,
        'checks': ['Verified production v1 archive and all recorded project inputs',
                   'Only Wine debug initialization and channel flags changed; no runtime.c code change',
                   'All FEX adapters, build options, linked dependencies and PE payloads match v1'],
    }
    (work / 'baseline-regression.json').write_bytes(p.enc(report))
    print(json.dumps({key: value for key, value in report.items() if key != 'recovered_helpers'}, indent=2))


if __name__ == '__main__':
    main()
