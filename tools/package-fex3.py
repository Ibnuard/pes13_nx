"""Package one isolated FEX3 NRO with test and PES launch modes (no game data)."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import zipfile
import pefile
import capstone
from nro_assets import inspect_nro

PROJECT = Path(__file__).resolve().parents[1]
WORK = PROJECT / 'local/fex3'
ROOT = 'switch/pes13-fex/'
FEX_SHA = '22ad6747d1b8a1f46e4da95eb760a7a596dadc76c8278fd9c8b62d0c677dd968'
DXVK_SHA = '265888c31ca78dffa290c39cb7e50bfb02762590e41927906e46fb32f01497fa'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module-dir', type=Path, default=WORK / 'native-lookup/module')
    parser.add_argument('--name', default='pes13-fex3-native-lookup')
    args = parser.parse_args()
    if not args.name.startswith('pes13-fex3-') or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.name):
        raise SystemExit('Use a simple pes13-fex3-* package name inside dist/.')
    module = args.module_dir.resolve()
    recipe = json.loads((WORK / 'runtime-build.json').read_text())
    fex = json.loads((module / 'build.json').read_text())
    assert fex['fex_commit'] == 'e2f973fe931e6dc2ce523795e51ca1ac3ca85816' and fex['horizon_adapter']
    for name, expected in fex['adapter_sources'].items():
        assert sha((PROJECT / name).read_bytes()) == expected, f'Rebuild FEX module after changing {name}'
    elf_sha = sha((WORK / 'reference/pes13-fex.elf').read_bytes())
    assert elf_sha == recipe['native_elf_sha256']
    for name, expected in recipe['adapter_sources'].items():
        assert sha((PROJECT / 'src/fex' / name).read_bytes()) == expected, f'Rebuild after changing {name}'
    for name, expected in recipe['patch_sources'].items():
        assert sha((PROJECT / name).read_bytes()) == expected, f'Rebuild after changing {name}'
    tests = {}
    for name in ('exception-tests', 'dispatcher-tests'):
        tests[name] = json.loads((WORK / (name+'.json')).read_text())
        assert tests[name]['passed'] and tests[name]['native_elf_sha256'] == elf_sha
    tests['guest-reference'] = json.loads((WORK / 'guest-reference.json').read_text())
    assert tests['guest-reference']['passed'] and tests['guest-reference']['guest_sha256'] == recipe['guest_sha256']
    # Do not publish workstation paths in the package's test report.
    tests['guest-reference'].pop('log', None)
    tests['smc'] = json.loads((module.parent / 'smc-tests.json').read_text())
    assert tests['smc']['passed'] and tests['smc']['dll_sha256'] == fex['sha256']
    assert tests['smc']['policy_sha256'] == sha((PROJECT / 'src/fex/horizon_smc.h').read_bytes())
    tests['memory'] = json.loads((module.parent / 'memory-tests.json').read_text())
    assert tests['memory']['passed'] and tests['memory']['dll_sha256'] == fex['sha256']
    assert tests['memory']['lookup_bytes_per_thread'] == 1024 * 1024
    tests['lookup'] = json.loads((module.parent / 'lookup-tests.json').read_text())
    assert tests['lookup']['passed'] and tests['lookup']['dll_sha256'] == fex['sha256']
    assert tests['lookup']['pressure_after']['live_caches'] >= 32
    assert tests['lookup']['invalidations'] >= 120 and tests['lookup']['dynamic_transitions'] >= 16
    tests['native-lookup'] = json.loads((module.parent / 'native-lookup-tests.json').read_text())
    assert tests['native-lookup']['passed'] and tests['native-lookup']['dll_sha256'] == fex['sha256']
    assert tests['native-lookup']['before_lookup_read_faults'] == 2
    assert tests['native-lookup']['before_commit_status'] == 'c0000022'
    assert tests['native-lookup']['native_lookup_nt_commits'] == 0
    assert tests['native-lookup']['native_lookup_clears'] >= 16
    tests['scratch'] = json.loads((module.parent / 'scratch-tests.json').read_text())
    assert tests['scratch']['passed'] and tests['scratch']['dll_sha256'] == fex['sha256']
    assert tests['scratch']['pressure_before']['null_published']
    assert tests['scratch']['pressure_after']['clients_served'] >= 32
    assert tests['scratch']['pressure_after']['reserved_bytes'] == 16 * 1024 * 1024
    assert not tests['scratch']['pressure_after']['null_published']
    assert not tests['scratch']['pressure_after']['stopped']
    tests['heap'] = json.loads((module.parent / 'heap-tests.json').read_text())
    assert tests['heap']['passed'] and tests['heap']['dll_sha256'] == fex['sha256']
    assert tests['heap']['span_reserved_bytes_after'] == 8 * 1024 * 1024
    assert tests['heap']['ntdll_sha256'] == recipe['ntdll_sha256']
    tests['alloc'] = json.loads((module.parent / 'alloc-tests.json').read_text())
    assert tests['alloc']['passed'] and tests['alloc']['dll_sha256'] == fex['sha256']
    tests['guest-trace'] = json.loads((module.parent / 'guest-trace-tests.json').read_text())
    assert tests['guest-trace']['passed'] and tests['guest-trace']['dll_sha256'] == fex['sha256']
    tests['unwind'] = json.loads((WORK / 'unwind-tests.json').read_text())
    assert tests['unwind']['passed'] and tests['unwind']['shared_index_export']
    assert tests['unwind']['native_elf_sha256'] == elf_sha
    assert tests['unwind']['fex_sha256'] == fex['sha256']
    assert tests['unwind']['ntdll_sha256'] == recipe['ntdll_sha256']
    assert tests['unwind']['wow64_sha256'] == recipe['wow64_sha256']
    assert tests['unwind']['tree_operations'] >= 576
    tests['reservations'] = json.loads((WORK / 'reservation-tests.json').read_text())
    assert tests['reservations']['passed'] and not tests['reservations']['baseline_reproduction']
    assert tests['reservations']['native_elf_sha256'] == elf_sha
    tests['thread-exit'] = json.loads((WORK / 'thread-exit-tests.json').read_text())
    assert tests['thread-exit']['passed'] and tests['thread-exit']['native_elf_sha256'] == elf_sha
    assert tests['thread-exit']['fex_sha256'] == fex['sha256']
    tests['fd-routing'] = json.loads((module.parent / 'fd-routing-tests.json').read_text())
    assert tests['fd-routing']['passed'] and tests['fd-routing']['native_elf_sha256'] == elf_sha
    assert tests['fd-routing']['before']['reproduced'] and tests['fd-routing']['scenarios'] >= 19
    tests['code-growth'] = json.loads((module.parent / 'code-growth-tests.json').read_text())
    assert tests['code-growth']['passed'] and tests['code-growth']['dll_sha256'] == fex['sha256']
    assert tests['code-growth']['before']['stopped_without_fallback']
    assert tests['code-growth']['scenario_count'] >= 17
    growth_scenarios = {row['scenario'] for row in tests['code-growth']['scenarios']}
    assert {'initial_64_MiB_reserves_32_MiB_without_rollover',
            'initial_64_MiB_falls_back_to_32_MiB_early'} <= growth_scenarios
    tests['jit-native'] = json.loads((module.parent / 'jit-native-tests.json').read_text())
    assert tests['jit-native']['passed'] and tests['jit-native']['native_elf_sha256'] == elf_sha
    assert tests['jit-native']['cases'] >= 12
    assert all(row['null_kernel_maps'] == 1 and row['result'] == '0xdc01'
               for row in tests['jit-native']['before_null_alias_reproduction'].values())
    tests['host-abi'] = json.loads((module.parent / 'abi-tests.json').read_text())
    assert tests['host-abi']['passed'] and tests['host-abi']['dll_sha256'] == fex['sha256']
    assert any('all seven callbacks' in check for check in tests['host-abi']['checks'])
    manifest = json.loads((PROJECT / 'config/runtime-files.json').read_text())
    sources = [PROJECT / p for p in ('local/legacy-cleanup/wine',
                                     'local/legacy-cleanup/pes13-port/sd-payload/switch/wine',
                                     'local/perf16/import-stage')]
    files = {}
    replacements = {'drive_c/windows/system32/winebox64.dll',
                    'drive_c/windows/system32/wow64.dll',
                    'drive_c/windows/system32/ntdll.dll', 'drive_c/dxvk/d3d9.dll'}
    for row in manifest:
        name = row['path']
        if name in replacements:
            continue
        for source in sources:
            candidate = source / name
            if not candidate.is_file() or candidate.stat().st_size != row['bytes']:
                continue
            data = candidate.read_bytes()
            if sha(data) == row['sha256']:
                files[ROOT+name] = data
                break
        else:
            raise RuntimeError(f'Matched dependency unavailable: {name}')
    for source, name, expected in (
        (WORK / 'payload/pes13-fex.nro', 'pes13-fex.nro', recipe['nro_sha256']),
        (WORK / 'payload/wow64.dll', 'drive_c/windows/system32/wow64.dll', recipe['wow64_sha256']),
        (WORK / 'payload/ntdll.dll', 'drive_c/windows/system32/ntdll.dll', recipe['ntdll_sha256']),
        (module / 'libwow64fex.dll', 'drive_c/windows/system32/libwow64fex.dll', fex['sha256']),
        (WORK / 'payload/fex-stress.exe', 'drive_c/fex-stress.exe', recipe['guest_sha256']),
    ):
        data = source.read_bytes()
        assert sha(data) == expected, source
        files[ROOT+name] = data
    with zipfile.ZipFile(PROJECT / 'dist/pes13-perf42-startup-guard.zip') as baseline:
        dxvk = baseline.read('switch/pes13-nx/drive_c/PES13/d3d9.dll')
    assert sha(dxvk) == DXVK_SHA
    for name in ('drive_c/PES13/d3d9.dll', 'drive_c/dxvk/d3d9.dll'):
        files[ROOT+name] = dxvk
    files[ROOT+'configuration.ini'] = (PROJECT / 'config/fex/configuration.ini').read_bytes()
    # Keep the reviewed preset source; install it at the path actually observed
    # in Settings Debug and confirmed by the user's working Box64 game.
    preset = 'drive_c/KONAMI/Pro Evolution Soccer 2013/settings.dat'
    preset_source = PROJECT / 'config/drive_c/users/steamuser/Documents/KONAMI/Pro Evolution Soccer 2013/settings.dat'
    files[ROOT+preset] = preset_source.read_bytes()
    for name in ('drive_c/PES13/pes2013.wine-nx.txt', 'drive_c/PES13/pes2013.keys.txt'):
        files[ROOT+name] = (PROJECT / 'config' / name).read_bytes()
    metadata = inspect_nro(files[ROOT+'pes13-fex.nro'], (PROJECT / 'assets/icon.jpg').read_bytes(),
                           expected_title='PES13-NX FEX3', expected_version='0.3.0')
    files['FEX3-INTEGRATION.md'] = (PROJECT / 'docs/FEX3-INTEGRATION.md').read_bytes()
    files['THIRD_PARTY.md'] = (PROJECT / 'THIRD_PARTY.md').read_bytes()
    files['README.txt'] = (
        'PES13-NX FEX3 native L1 lookup memory - hardware retest required\n\n'
        'The latest PES run shows the intro, then a rejected Wine memory\n'
        'commit causes a native FindBlock access violation and parks a thread.\n'
        'This candidate allocates and clears the L2-off lookup table on the\n'
        'native heap before use, eliminating lazy Wine commits for that L1.\n'
        'The prior rejected-suspend backoff and JIT cache fixes stay included.\n'
        'Code-cache turnover may still cause stutter; no FPS gain is verified.\n'
        'Read FEX3-INTEGRATION.md for complete setup and test steps.\n'
        'Extract switch/ at the SD root. One NRO: switch/pes13-fex/pes13-fex.nro.\n'
        'Forwarder: full application, 32-bit address space, no alias, 4 cores.\n'
        'Default configuration.ini run_guest_tests=1 runs the original test.\n'
        'Expected: [FEX3-FAULT] PASS and [FEX3-GUEST] PASS all checks.\n'
        'After PASS, close with HOME -> X. Copy your own installed game, private\n'
        'pes13-install.reg and working drive_c/KONAMI/ profile into the FEX prefix.\n'
        'Reapply the package after copying game DLLs, then copy your profile.\n'
        'Set run_guest_tests=0 to launch PES with the same NRO.\n'
        'Logs: switch/pes13-fex/fex-runtime.log and drive_c/fex-guest.log.\n'
        'Save logs before the next launch. Test PASS is not a game FPS result.\n'
        'Keep the working Box64 prefix separate; do not replace its NRO/DLLs.\n'
    ).encode()
    files['licenses/Wine-and-PES13-LGPL-2.1.txt'] = (PROJECT / 'LICENSE').read_bytes()
    files['licenses/PES13-FEX-adapter-MIT.txt'] = (PROJECT / 'src/fex/LICENSE').read_bytes()
    for path in (PROJECT / 'licenses').rglob('*'):
        if path.is_file() and path.name != 'Box64-LICENSE.txt':
            files[path.relative_to(PROJECT).as_posix()] = path.read_bytes()
    for path in (module / 'licenses').rglob('*'):
        if path.is_file():
            files['licenses/FEX/'+path.relative_to(module / 'licenses').as_posix()] = path.read_bytes()
    assert 'licenses/FEX/LICENSE' in files and 'licenses/DXVK-LICENSE.txt' in files
    assert sum(n.endswith('.nro') for n in files) == 1
    assert [n for n in files if n.endswith('.exe')] == [ROOT+'drive_c/fex-stress.exe']
    assert [n for n in files if n.endswith('.dat')] == [ROOT+preset]
    assert not any(n.endswith(('.reg', '.log')) or 'winebox64.dll' in n or 'rld.dll' in n for n in files)
    target = PROJECT / 'dist' / args.name
    if target.exists():
        extras = {p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()} - set(files) - {'FEX3-manifest.json'}
        if extras:
            raise RuntimeError(f'Preserving unexpected files; use a clean output directory: {extras}')
    for name, data in files.items():
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    spec = importlib.util.spec_from_file_location('audit_fex_imports', PROJECT / 'tools/audit-fex-imports.py')
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    prefix = target / ROOT
    native, guest = prefix / 'drive_c/windows/system32', prefix / 'drive_c/windows/syswow64'
    reports = {name: audit.audit(native / (name+'.dll'), native) for name in ('ntdll', 'libwow64fex', 'wow64', 'wow64win')}
    reports['guest'] = audit.audit(prefix / 'drive_c/fex-stress.exe', guest, machine=0x14c)
    for name, result in reports.items():
        (WORK / (name+'-imports.json')).write_text(json.dumps(result, indent=2)+'\n')
        assert result['passed'], (name, result['issues'])
    record = {'kind': 'FEX3 resident native L1 lookup experiment', 'fex_commit': fex['fex_commit'],
              'on_device_tested': False, 'game_included': False, 'metadata': metadata,
              'fex2_proven_dll_sha256': FEX_SHA, 'fex_dll_sha256': fex['sha256'], 'dxvk_sha256': DXVK_SHA,
              'latest_hardware_observation': 'Suspend-backoff run shows choppy intro video; a 20 KiB lazy L1 commit returns c0000022, FindBlock faults, a thread parks and presents stop at 1534',
              'earlier_hardware_failure': 'FD-routing PES run presented frames, then jitCreate 64 MiB returned 0xdc01; executable allocation failure trapped and parked a thread',
              'previous_guest_checkpoint': 'Complete original stress PASS on reserve-fix: 4 waves, 16 workers, 256 automatic SMC updates and 256 handled guest faults',
              'previous_native_fault_checkpoint': 'PASS 64 roundtrips; 4 overlapping handlers; all slots released',
              'box64_engine_linked': recipe['box64_engine_linked'],
              'local_tests': tests, 'static_fex_and_test_imports_passed': True,
              'files': {name: sha(data) for name, data in sorted(files.items())}}
    files['FEX3-manifest.json'] = (json.dumps(record, indent=2)+'\n').encode()
    (target / 'FEX3-manifest.json').write_bytes(files['FEX3-manifest.json'])
    archive = target.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 25, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert all(z.read(name) == data for name, data in files.items())
    report = {'path': str(archive), 'bytes': archive.stat().st_size, 'sha256': sha(archive.read_bytes()),
              'files': len(files), 'imports_passed': True, 'nro_sha256': recipe['nro_sha256']}
    # Keep the preceding suspend backoff when updating any ABI-2 installation.
    # Neither these DLL changes nor native lookup allocation changes host ABI.
    # The update excludes the NRO, configuration and user game/profile data.
    update_names = ('drive_c/windows/system32/libwow64fex.dll',
                    'drive_c/windows/system32/ntdll.dll')
    update = {ROOT+name: files[ROOT+name] for name in update_names}
    for name, data in files.items():
        if name.startswith('licenses/') or name in ('FEX3-INTEGRATION.md', 'THIRD_PARTY.md'):
            update[name] = data
    update['README.txt'] = (
        'PES13-NX FEX3 native L1 lookup - existing ABI-2 FEX3 update\n\n'
        'Close the application with HOME -> X before copying.\n'
        'Extract switch/ to the SD root, replacing the two ARM64 system32\n'
        'DLLs: libwow64fex.dll and ntdll.dll. Keep the existing ABI-2 NRO,\n'
        'forwarder, configuration.ini, game and profile.\n'
        'Keep run_guest_tests=0 for PES mode. Save fex-runtime.log before\n'
        'reopening, since startup overwrites it. Try two separate launches.\n'
        'Check [FEX3-LOOKUP] L2=off native=1 MiB/thread; no lazy commits.\n'
        'Record whether the intro/menu appears and whether vk_presents\n'
        'keeps advancing. Save the log if the video freezes again.\n'
        'This targets the observed lookup crash; Switch results are pending.\n'
        'If ABI 2 is not already installed, use the full package.\n'
    ).encode()
    update['FEX3-update-manifest.json'] = (json.dumps({
        'kind': 'existing ABI-2 FEX3 installation resident native L1 update', 'on_device_tested': False,
        'required_nro_sha256': recipe['nro_sha256'],
        'included_fex_dll_sha256': fex['sha256'],
        'required_wow64_sha256': recipe['wow64_sha256'],
        'included_ntdll_sha256': recipe['ntdll_sha256'],
        'complete_package_sha256': report['sha256'],
        'files': {name: sha(data) for name, data in sorted(update.items())},
    }, indent=2)+'\n').encode()
    update_archive = PROJECT / 'dist' / (args.name+'-update.zip')
    with zipfile.ZipFile(update_archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(update.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 25, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    with zipfile.ZipFile(update_archive) as z:
        assert z.testzip() is None
        assert all(z.read(name) == data for name, data in update.items())
        assert {name for name in z.namelist() if name.startswith(ROOT)} == {ROOT+name for name in update_names}
    report['update'] = {'path': str(update_archive), 'bytes': update_archive.stat().st_size,
                        'sha256': sha(update_archive.read_bytes())}
    previous_native = PROJECT / 'dist/pes13-fex3-suspend-backoff/switch/pes13-fex/drive_c/windows/system32'
    previous_data = (previous_native / 'libwow64fex.dll').read_bytes()
    previous_ntdll = (previous_native / 'ntdll.dll').read_bytes()
    assert sha(previous_data) == '70051eddb9dce9991239ca3f5ce40fce5f572c0888520e1c3e681b61b8a2f82d'
    assert sha(previous_ntdll) == recipe['ntdll_sha256']
    assert tests['native-lookup']['before_sha256'] == sha(previous_data)
    def pe_interface(data):
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
    assert pe_interface(previous_data) == pe_interface(files[ROOT+'drive_c/windows/system32/libwow64fex.dll'])
    def suspend_calls_delay(data):
        pe = pefile.PE(data=data)
        try:
            exports = sorted(symbol.address for symbol in pe.DIRECTORY_ENTRY_EXPORT.symbols if symbol.address)
            named = {symbol.name.decode(): symbol.address for symbol in pe.DIRECTORY_ENTRY_EXPORT.symbols if symbol.name}
            start = named['RtlWow64SuspendThread']
            end = next(address for address in exports if address > start)
            delay = named['NtDelayExecution']
            decoder = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
            return any(instruction.mnemonic == 'bl' and instruction.op_str == f'#{delay:#x}'
                       for instruction in decoder.disasm(pe.get_data(start, end-start), start))
        finally:
            pe.close()
    assert suspend_calls_delay(files[ROOT+'drive_c/windows/system32/ntdll.dll'])
    rollback_archive = PROJECT / 'dist' / (args.name+'-rollback.zip')
    rollback = {
        ROOT+'drive_c/windows/system32/libwow64fex.dll': previous_data,
        ROOT+'drive_c/windows/system32/ntdll.dll': previous_ntdll,
        'README.txt': (
            'PES13-NX FEX3 native L1 lookup rollback. Close via HOME -> X, then\n'
            'extract switch/ at the SD root. Restores the preceding native-scratch\n'
            'FEX DLL and retains the rejected-suspend backoff in ARM64 ntdll.\n'
            'NRO, configuration, game and profile are not included.\n'
        ).encode(),
    }
    for name, data in files.items():
        if name.startswith('licenses/') or name == 'THIRD_PARTY.md':
            rollback[name] = data
    with zipfile.ZipFile(rollback_archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(rollback.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 25, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    with zipfile.ZipFile(rollback_archive) as z:
        assert z.testzip() is None
        assert all(z.read(name) == data for name, data in rollback.items())
    report['rollback'] = {'path': str(rollback_archive), 'bytes': rollback_archive.stat().st_size,
                          'sha256': sha(rollback_archive.read_bytes()),
                          'restored_fex_dll_sha256': sha(previous_data),
                          'retained_ntdll_sha256': sha(previous_ntdll)}
    (WORK / 'package.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
