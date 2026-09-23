"""Package only the FEX2 probe, matched Wine dependencies, and original test."""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import zipfile
import pefile
from nro_assets import inspect_nro

project = Path(__file__).resolve().parents[1]
work = project / 'local/fex2'
sha = lambda data: hashlib.sha256(data).hexdigest()


def main():
    recipe = json.loads((work / 'runtime-build.json').read_text())
    fex = json.loads((work / 'module/build.json').read_text())
    allocation_tests = json.loads((work / 'heap-fix/allocation-tests.json').read_text())
    assert allocation_tests['passed'] and allocation_tests['dll_sha256'] == fex['sha256']
    counter_tests = json.loads((work / 'heap-fix/counter-tests.json').read_text())
    assert counter_tests['passed'] and counter_tests['dll_sha256'] == fex['sha256']
    abi_tests = json.loads((work / 'heap-fix/abi-tests.json').read_text())
    assert abi_tests['passed'] and abi_tests['dll_sha256'] == fex['sha256']
    assert abi_tests['native_elf_sha256'] == sha((work / 'reference/fex2.elf').read_bytes())
    heap_tests = json.loads((work / 'heap-fix/heap-tests.json').read_text())
    assert heap_tests['passed'] and heap_tests['dll_sha256'] == fex['sha256']
    patches = json.loads((work / 'module/patches.json').read_text())
    assert patches['submodule_commits']['External/rpmalloc'] == '09142d726429416bfa7b459151515fe3ab7622dd'
    reference = json.loads((work / 'guest-reference.json').read_text())
    assert reference['passed'] and reference['guest_sha256'] == recipe['guest_sha256']
    root = 'switch/pes13-fex2/'
    files = {}
    manifest = {row['path']: row for row in json.loads((project / 'config/runtime-files.json').read_text())}
    stage = project / 'local/perf16/import-stage'
    assert abi_tests['ntdll_sha256'] == sha((stage / 'drive_c/windows/system32/ntdll.dll').read_bytes())
    assert heap_tests['ntdll_sha256'] == abi_tests['ntdll_sha256']
    dependencies = [f'drive_c/windows/system32/{name}.dll' for name in
                    ('ntdll', 'apisetschema', 'win32u', 'wow64win')]
    dependencies += [f'drive_c/windows/syswow64/{name}.dll' for name in ('ntdll', 'kernel32', 'kernelbase')]
    for name in dependencies:
        data = (stage / name).read_bytes()
        assert sha(data) == manifest[name]['sha256'], name
        files[root + name] = data
    nls = project / 'local/legacy-cleanup/wine'
    for name, entry in manifest.items():
        if name.startswith('share/wine/nls/'):
            data = (nls / name).read_bytes()
            assert sha(data) == entry['sha256'], name
            files[root + name] = data
    for source, dest, expected in (
        (work / 'payload/pes13-fex2.nro', 'pes13-fex2.nro', recipe['nro_sha256']),
        (work / 'payload/wow64.dll', 'drive_c/windows/system32/wow64.dll', recipe['wow64_sha256']),
        (work / 'module/libwow64fex.dll', 'drive_c/windows/system32/libwow64fex.dll', fex['sha256']),
        (work / 'payload/fex-smoke.exe', 'drive_c/fex-smoke.exe', recipe['guest_sha256']),
    ):
        data = source.read_bytes()
        assert sha(data) == expected, source
        files[root + dest] = data
    metadata = inspect_nro(files[root + 'pes13-fex2.nro'], (project / 'assets/icon.jpg').read_bytes(),
                           expected_title='PES13 FEX2 x86 Test', expected_version='0.2.0')
    files['README.txt'] = (
        'PES13 FEX2 compact heap fix (experimental x86 integration test)\n\n'
        'Copy switch/ from this ZIP to the SD root and replace existing files.\n'
        'No PES/game files are needed. The NRO path is unchanged; an existing\n'
        'FEX2 forwarder can be reused. This includes the earlier allocation,\n'
        'counter and x18 callback fixes, plus a compact 32 MiB heap span layout.\n'
        'A normal span reservation is now 64 MiB including alignment padding,\n'
        'instead of 512 MiB. Physical pages are still committed as needed.\n'
        'Open switch/pes13-fex2/pes13-fex2.nro in full application mode.\n'
        'For Sphaira use 32-bit address space, no alias, 4 cores as in FEX1.\n'
        'This package uses its own prefix; leave switch/pes13-nx/ alone.\n\n'
        'First the console should report [FEX2-HOST] PASS for full context restore.\n'
        '[FEX2-ABI] PASS checks the Wine thread register across a native log call.\n'
        'Before CRT initialization, [FEX2-ALLOC] PASS checks memory allocation.\n'
        '[FEX2-TIMER] PASS checks CNTPCT_EL0, followed by process CRT ready.\n'
        '[FEX2-HEAP] PASS then checks real small/medium/large heap blocks.\n'
        'Then Wine loads libwow64fex.dll and runs the original fex-smoke.exe.\n'
        'A successful guest run ends with [FEX2-GUEST] PASS all checks in\n'
        'switch/pes13-fex2/drive_c/fex-guest.log and a process exit code of 0.\n'
        'The runtime parks after exit: HOME -> X -> Close is expected.\n'
        'Allow up to 60 seconds for first initialization. If it stops or fails,\n'
        'close from HOME and return the logs; do not replace DLLs individually.\n\n'
        'Return both files when present:\n'
        '  switch/pes13-fex2/fex-runtime.log\n'
        '  switch/pes13-fex2/drive_c/fex-guest.log\n'
        'A missing guest log means the guest did not reach its first file write.\n'
        'Tests do not measure game FPS. Actual FEX guest execution on Switch\n'
        'has not been validated before this package is supplied for testing.\n'
    ).encode()
    files['FEX2-BRINGUP.md'] = (project / 'docs/FEX2-BRINGUP.md').read_bytes()
    files['THIRD_PARTY.md'] = (project / 'THIRD_PARTY.md').read_bytes()
    files['licenses/Wine-and-PES13-LGPL-2.1.txt'] = (project / 'LICENSE').read_bytes()
    files['licenses/PES13-FEX-adapter-MIT.txt'] = (project / 'src/fex/LICENSE').read_bytes()
    for path in (project / 'licenses').rglob('*'):
        if path.is_file() and path.name not in ('Box64-LICENSE.txt', 'DXVK-LICENSE.txt'):
            files[path.relative_to(project).as_posix()] = path.read_bytes()
    for path in (work / 'module/licenses').rglob('*'):
        if path.is_file():
            files['licenses/FEX/' + path.relative_to(work / 'module/licenses').as_posix()] = path.read_bytes()
    assert 'licenses/FEX/LICENSE' in files
    assert sum(name.endswith('.nro') for name in files) == 1
    assert [name for name in files if name.endswith('.exe')] == [root + 'drive_c/fex-smoke.exe']
    assert not any(name.endswith(('.reg', '.dat', '.log')) or '/PES13/' in name or
                   'winebox64.dll' in name or '/dxvk/' in name for name in files)
    target = project / 'dist/pes13-fex2-heap-fix'
    # Only overwrite files produced by this exact package builder. A log from
    # a device run, or any other extra file, is preserved and blocks packaging.
    if target.exists():
        extras = {p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()} - set(files) - {'FEX2-manifest.json'}
        if extras:
            raise RuntimeError(f'Unexpected files in package directory: {extras}')
    for name, data in files.items():
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    spec = importlib.util.spec_from_file_location('audit_fex_imports', project / 'tools/audit-fex-imports.py')
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    dll_dir = target / root / 'drive_c/windows/system32'
    guest_dir = target / root / 'drive_c/windows/syswow64'
    reports = {
        'fex': audit.audit(dll_dir / 'libwow64fex.dll', dll_dir),
        'wow64win': audit.audit(dll_dir / 'wow64win.dll', dll_dir),
        'guest': audit.audit(target / root / 'drive_c/fex-smoke.exe', guest_dir, machine=0x14c),
    }
    for name, result in reports.items():
        (work / f'{name}-imports.json').write_text(json.dumps(result, indent=2) + '\n')
        assert result['passed'], (name, result['issues'])
    with pefile.PE(data=files[root + 'drive_c/windows/system32/libwow64fex.dll']) as pe:
        names = {s.name for s in pe.DIRECTORY_ENTRY_EXPORT.symbols}
        assert {b'PES13FexSetHost', b'PES13FexHandleException', b'BTCpuSimulate'} <= names
    record = {'kind': 'FEX2 compact heap fix and original x86 test', 'fex_commit': fex['fex_commit'],
              'submodule_commits': patches['submodule_commits'],
              'metadata': metadata, 'on_device_tested': False, 'game_included': False,
              'allocation_test': allocation_tests,
              'counter_test': counter_tests,
              'abi_test': abi_tests,
              'heap_test': heap_tests,
              'files': {name: sha(data) for name, data in sorted(files.items())}}
    files['FEX2-manifest.json'] = (json.dumps(record, indent=2) + '\n').encode()
    (target / 'FEX2-manifest.json').write_bytes(files['FEX2-manifest.json'])
    archive = target.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 24, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert all(z.read(name) == data for name, data in files.items())
    report = {'path': str(archive), 'bytes': archive.stat().st_size,
              'sha256': sha(archive.read_bytes()), 'files': len(files),
              'imports_passed': True, 'nro_sha256': recipe['nro_sha256']}
    (work / 'package-heap-fix.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
