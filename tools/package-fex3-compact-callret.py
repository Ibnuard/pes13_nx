"""Build a verified one-DLL update/rollback for the existing ABI-2 FEX prefix."""
from pathlib import Path
import hashlib
import json
import zipfile

import pefile


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'local/fex3'
PREVIOUS = WORK / 'early-128/module'
CURRENT = WORK / 'compact-callret/module'
SD_DLL = 'switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll'
OLD_SHA = 'b3f229ded7202f9a6c93cf9fc502dd6ded140e0191d128ab25fc50c9eacc51e7'
LOG_SHA = '046effb55464f126d6eba877c5fd8804185b33c0b840b60061a302a14292003e'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def interface(data):
    pe = pefile.PE(data=data)
    try:
        exports = {(s.name, s.ordinal, s.forwarder) for s in pe.DIRECTORY_ENTRY_EXPORT.symbols}
        imports = {(directory, dep.dll, tuple((e.name, e.ordinal) for e in dep.imports))
                   for directory in ('DIRECTORY_ENTRY_IMPORT', 'DIRECTORY_ENTRY_DELAY_IMPORT')
                   for dep in getattr(pe, directory, [])}
        return pe.FILE_HEADER.Machine, exports, imports
    finally:
        pe.close()


def archive(name, files):
    target = ROOT / 'dist' / name
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        for path, data in sorted(files.items()):
            info = zipfile.ZipInfo(path, (2026, 9, 25, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        assert set(z.namelist()) == set(files)
        assert all(z.read(path) == data for path, data in files.items())
        assert {path for path in z.namelist() if path.startswith('switch/')} == {SD_DLL}
    return {'path': str(target), 'bytes': target.stat().st_size,
            'sha256': digest(target.read_bytes())}


def main():
    old_build = json.loads((PREVIOUS / 'build.json').read_text())
    new_build = json.loads((CURRENT / 'build.json').read_text())
    old = (PREVIOUS / 'libwow64fex.dll').read_bytes()
    new = (CURRENT / 'libwow64fex.dll').read_bytes()
    assert digest(old) == old_build['sha256'] == OLD_SHA
    assert digest(new) == new_build['sha256'] and old != new
    assert old_build['fex_commit'] == new_build['fex_commit']
    assert old_build['horizon_adapter'] and new_build['horizon_adapter']
    assert interface(old) == interface(new), 'FEX DLL import/export ABI changed'
    assert interface(new)[0] == 0xaa64

    def patches(module):
        return {row['path']: row['patched_sha256']
                for row in json.loads((module / 'patches.json').read_text())['files']}

    previous, current = patches(PREVIOUS), patches(CURRENT)
    changed = {p for p in previous.keys() | current.keys() if previous.get(p) != current.get(p)}
    assert changed == {'Source/Windows/WOW64/Module.cpp',
                       'FEXCore/include/FEXCore/Debug/InternalThreadState.h',
                       'Source/Windows/Common/CallRetStack.h'}, changed
    assert all(old_build['adapter_sources'][name] == value
               for name, value in new_build['adapter_sources'].items()
               if name != 'tools/fex_horizon_patches.py')
    assert all(digest((ROOT / name).read_bytes()) == value
               for name, value in new_build['adapter_sources'].items())

    test_names = ('callret', 'code-growth', 'native-lookup', 'lookup', 'scratch',
                  'smc', 'memory', 'alloc', 'guest-trace', 'abi', 'unwind', 'thread-exit')
    tests = {name: json.loads((CURRENT.parent / (name + '-tests.json')).read_text())
             for name in test_names}
    assert all(r['passed'] and r.get('dll_sha256', r.get('fex_sha256')) == digest(new)
               for r in tests.values())
    assert tests['callret']['before_sha256'] == OLD_SHA
    assert tests['callret']['saved_committed_bytes'] == 133693440
    assert tests['callret']['guard_recoveries'] == {'push': 9, 'pop': 1}
    assert tests['code-growth']['scenario_count'] >= 17
    scenarios = {row['scenario'] for row in tests['code-growth']['scenarios']}
    assert {'initial_128_MiB_reserves_32_MiB_without_rollover',
            'initial_128_MiB_falls_back_to_32_MiB_early'} <= scenarios
    assert tests['native-lookup']['native_lookup_nt_commits'] == 0
    assert tests['lookup']['invalidations'] >= 120
    assert tests['scratch']['pressure_after']['clients_served'] >= 32

    runtime = json.loads((WORK / 'runtime-build.json').read_text())
    assert digest((WORK / 'payload/pes13-fex.nro').read_bytes()) == runtime['nro_sha256']
    assert digest((WORK / 'team-memory/before/fex-runtime.log').read_bytes()) == LOG_SHA
    common = {
        'FEX3-INTEGRATION.md': (ROOT / 'docs/FEX3-INTEGRATION.md').read_bytes(),
        'FEX3-RESULT.md': (ROOT / 'docs/FEX3-RESULT.md').read_bytes(),
        'THIRD_PARTY.md': (ROOT / 'THIRD_PARTY.md').read_bytes(),
        'licenses/FEX/LICENSE': (CURRENT / 'licenses/LICENSE').read_bytes(),
        'licenses/PES13-FEX-adapter-MIT.txt': (ROOT / 'src/fex/LICENSE').read_bytes(),
    }
    for name in test_names:
        common['validation/' + name + '-tests.json'] = (CURRENT.parent / (name + '-tests.json')).read_bytes()
    evidence = {
        'kind': 'compact FEX CALL/RET prediction cache', 'on_device_tested': False,
        'previous_fex_dll_sha256': digest(old), 'candidate_fex_dll_sha256': digest(new),
        'required_nro_sha256': runtime['nro_sha256'], 'fex_commit': new_build['fex_commit'],
        'changed_upstream_files': sorted(changed), 'hardware_log_sha256': LOG_SHA,
        'prediction_bytes_per_thread': 262144, 'initial_code_bytes': 134217728,
        'modeled_saving_at_34_threads_bytes': 133693440,
        'linked_arm64_tests': {name: {'passed': r['passed'],
                                      'dll_sha256': r.get('dll_sha256', r.get('fex_sha256'))}
                              for name, r in tests.items()},
    }
    common['FEX3-compact-callret-manifest.json'] = (json.dumps(evidence, indent=2)+'\n').encode()
    update = dict(common, **{
        SD_DLL: new,
        'README.txt': (
            'PES13-NX FEX3 compact CALL/RET cache candidate\n\n'
            'For the existing early-128 ABI-2 FEX installation. Close with\n'
            'HOME -> X. Extract this ZIP at the SD root, replacing only\n'
            'switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll.\n'
            'The NRO, ntdll, configuration, game and profile remain in use.\n'
            'Leave run_guest_tests=0 for PES. Startup should print:\n'
            '[FEX3-CALLRET] v1 prediction stack=256 KiB/thread; guard recovery retained\n\n'
            'Test Exhibition -> controller -> team selection, then a match.\n'
            'Save fex-runtime.log before relaunching, including terminal lines\n'
            'if the picture stops. The initial code cache remains 128 MiB.\n'
            'This reduces prediction-cache memory, not the guest program stack.\n'
            'Smaller capacity can increase guard recovery for deep/unbalanced\n'
            'calls. Linked ARM64 tests pass; the Switch result is unverified.\n'
        ).encode(),
    })
    rollback = {
        SD_DLL: old,
        'licenses/FEX/LICENSE': common['licenses/FEX/LICENSE'],
        'licenses/PES13-FEX-adapter-MIT.txt': common['licenses/PES13-FEX-adapter-MIT.txt'],
        'THIRD_PARTY.md': common['THIRD_PARTY.md'],
        'FEX3-compact-callret-manifest.json': (json.dumps({
            'kind': 'compact-callret rollback to menu-reaching early-128',
            'restored_fex_dll_sha256': digest(old), 'replaced_candidate_fex_dll_sha256': digest(new),
            'required_nro_sha256': runtime['nro_sha256'],
        }, indent=2)+'\n').encode(),
        'README.txt': (
            'PES13-NX FEX3 compact-callret rollback\n\n'
            'Close through HOME -> X; extract at the SD root. Restores the\n'
            'exact early-128 FEX DLL that reached the menu, without changing\n'
            'the NRO, ntdll, configuration, game or profile.\n'
        ).encode(),
    }
    report = {'update': archive('pes13-fex3-compact-callret-update.zip', update),
              'rollback': archive('pes13-fex3-compact-callret-rollback.zip', rollback),
              'candidate_fex_dll_sha256': digest(new), 'previous_fex_dll_sha256': digest(old),
              'tests': list(test_names)}
    (CURRENT.parent / 'package.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
