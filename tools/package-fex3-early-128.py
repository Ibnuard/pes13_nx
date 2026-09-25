"""Package an isolated FEX code-reserve A/B update for an existing ABI-2 prefix."""

from pathlib import Path
import hashlib
import json
import zipfile

import pefile


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'local/fex3'
PREVIOUS = WORK / 'native-lookup/module'
CURRENT = WORK / 'early-128/module'
SD_DLL = 'switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def interface(data):
    pe = pefile.PE(data=data)
    try:
        exports = {(symbol.name, symbol.ordinal, symbol.forwarder)
                   for symbol in pe.DIRECTORY_ENTRY_EXPORT.symbols}
        imports = {(directory, dep.dll,
                    tuple((entry.name, entry.ordinal) for entry in dep.imports))
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
    assert digest(old) == old_build['sha256'] == '226d207d075fc967f24074e04f72bc97ab181a9bff8a8271c937c3939b511b82'
    assert digest(new) == new_build['sha256'] and old != new
    assert old_build['fex_commit'] == new_build['fex_commit']
    assert old_build['horizon_adapter'] and new_build['horizon_adapter']
    assert interface(old) == interface(new), 'FEX DLL import/export ABI changed'

    def patches(module):
        return {row['path']: row['patched_sha256']
                for row in json.loads((module / 'patches.json').read_text())['files']}

    previous_patches, current_patches = patches(PREVIOUS), patches(CURRENT)
    changed = {path for path in previous_patches.keys() | current_patches.keys()
               if previous_patches.get(path) != current_patches.get(path)}
    assert changed == {'FEXCore/Source/Interface/Core/SharedCodeBufferManager.cpp'}, changed
    assert all(old_build['adapter_sources'][name] == value
               for name, value in new_build['adapter_sources'].items()
               if name != 'tools/fex_horizon_patches.py')

    test_names = ('code-growth', 'native-lookup', 'lookup', 'scratch',
                  'smc', 'memory', 'alloc', 'guest-trace', 'abi')
    tests = {name: json.loads((CURRENT.parent / (name + '-tests.json')).read_text())
             for name in test_names}
    assert all(result['passed'] and result['dll_sha256'] == digest(new)
               for result in tests.values())
    growth = tests['code-growth']
    assert growth['scenario_count'] >= 17 and growth['before']['stopped_without_fallback']
    scenarios = {row['scenario'] for row in growth['scenarios']}
    assert {'initial_128_MiB_reserves_32_MiB_without_rollover',
            'initial_128_MiB_falls_back_to_32_MiB_early'} <= scenarios
    assert tests['native-lookup']['native_lookup_nt_commits'] == 0
    assert tests['lookup']['invalidations'] >= 120
    assert tests['scratch']['pressure_after']['clients_served'] >= 32

    runtime = json.loads((WORK / 'runtime-build.json').read_text())
    assert digest((WORK / 'payload/pes13-fex.nro').read_bytes()) == runtime['nro_sha256']
    common = {
        'FEX3-INTEGRATION.md': (ROOT / 'docs/FEX3-INTEGRATION.md').read_bytes(),
        'FEX3-RESULT.md': (ROOT / 'docs/FEX3-RESULT.md').read_bytes(),
        'THIRD_PARTY.md': (ROOT / 'THIRD_PARTY.md').read_bytes(),
        'licenses/FEX/LICENSE': (CURRENT / 'licenses/LICENSE').read_bytes(),
        'licenses/PES13-FEX-adapter-MIT.txt': (ROOT / 'src/fex/LICENSE').read_bytes(),
    }
    evidence = {
        'kind': 'early 128 MiB FEX executable cache experiment',
        'on_device_tested': False,
        'previous_fex_dll_sha256': digest(old),
        'candidate_fex_dll_sha256': digest(new),
        'required_nro_sha256': runtime['nro_sha256'],
        'fex_commit': new_build['fex_commit'],
        'changed_upstream_file': next(iter(changed)),
        'linked_arm64_tests': {name: {'passed': value['passed'],
                                     'dll_sha256': value['dll_sha256']}
                               for name, value in tests.items()},
        'hardware_log_sha256': '62b320a69384b437c680471f03e4f8bb70cbf7db4920290859401c9bccbab9b0',
    }
    common['FEX3-early-128-manifest.json'] = (json.dumps(evidence, indent=2) + '\n').encode()
    update = dict(common, **{
        SD_DLL: new,
        'README.txt': (
            'PES13-NX FEX3 early 128 MiB code-reserve experiment\n\n'
            'Requires the existing ABI-2 native-L1 FEX3 installation. Close it\n'
            'with HOME -> X. Extract this ZIP at the SD root, replacing only\n'
            'switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll.\n'
            'Keep NRO, ntdll.dll, configuration.ini, game and profile unchanged.\n'
            'For PES, leave run_guest_tests=0. Save fex-runtime.log before each\n'
            'relaunch. The first large [FEX-JIT] allocation should be 134217728\n'
            'bytes (128 MiB), or a smaller fallback if the alias cannot fit.\n'
            'Check whether intro video advances and whether [FEX3-CODE] STOP\n'
            'returns. Initial video slowness before cache rollover may remain.\n'
            'This candidate has not yet passed a Switch PES test.\n'
        ).encode(),
    })
    rollback = dict(common, **{
        SD_DLL: old,
        'FEX3-early-128-manifest.json': (json.dumps({
            'kind': 'early 128 MiB FEX executable cache rollback',
            'restored_fex_dll_sha256': digest(old),
            'replaced_candidate_fex_dll_sha256': digest(new),
            'required_nro_sha256': runtime['nro_sha256'],
        }, indent=2) + '\n').encode(),
        'README.txt': (
            'PES13-NX FEX3 early-128 rollback\n\n'
            'Close with HOME -> X; extract at the SD root. Restores the prior\n'
            'native-L1 FEX DLL without changing NRO, ntdll, game or profile.\n'
        ).encode(),
    })
    report = {'update': archive('pes13-fex3-early-128-update.zip', update),
              'rollback': archive('pes13-fex3-early-128-rollback.zip', rollback),
              'candidate_fex_dll_sha256': digest(new),
              'previous_fex_dll_sha256': digest(old),
              'tests': list(test_names)}
    out = WORK / 'early-128/package.json'
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
