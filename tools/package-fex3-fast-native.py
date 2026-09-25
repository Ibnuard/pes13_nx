"""Package matched ABI-3 FEX native-heap profiles and the ABI-2 rollback."""
from pathlib import Path
import hashlib
import json
import zipfile

import pefile

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'local/fex3/fast-native'
PREVIOUS = ROOT / 'local/fex3/alias-perf'
PREFIX = 'switch/pes13-fex/'
NRO = PREFIX+'pes13-fex.nro'
DLL = PREFIX+'drive_c/windows/system32/libwow64fex.dll'
INI = PREFIX+'configuration.ini'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verified(path, report, field):
    data = path.read_bytes()
    assert sha(data) == json.loads(report.read_text())[field], path
    return data


def interface(data):
    pe = pefile.PE(data=data)
    try:
        return (pe.FILE_HEADER.Machine,
                {(s.name, s.ordinal, s.forwarder) for s in pe.DIRECTORY_ENTRY_EXPORT.symbols},
                {(kind, dep.dll, item.name, item.ordinal)
                 for kind in ('DIRECTORY_ENTRY_IMPORT', 'DIRECTORY_ENTRY_DELAY_IMPORT')
                 for dep in getattr(pe, kind, []) for item in dep.imports})
    finally:
        pe.close()


def archive(name, files, switch_paths):
    directory = ROOT / 'dist' / name
    directory.mkdir(parents=True, exist_ok=True)
    for relative, data in files.items():
        path = directory / relative
        assert path.resolve().is_relative_to(directory.resolve())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    target = directory.with_suffix('.zip')
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as output:
        for relative, data in sorted(files.items()):
            entry = zipfile.ZipInfo(relative, (2026, 9, 26, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            output.writestr(entry, data)
    with zipfile.ZipFile(target) as check:
        assert check.testzip() is None and set(check.namelist()) == set(files)
        assert {p for p in check.namelist() if p.startswith('switch/')} == switch_paths
        for path, data in files.items():
            assert check.read(path) == data
    return {'zip': str(target), 'directory': str(directory),
            'sha256': sha(target.read_bytes()), 'bytes': target.stat().st_size}


def main():
    module = json.loads((WORK/'module/build.json').read_text())
    runtime = json.loads((WORK/'runtime/runtime-build.json').read_text())
    dll = verified(WORK/'module/libwow64fex.dll', WORK/'module/build.json', 'sha256')
    nro = verified(WORK/'runtime/pes13-fex.nro', WORK/'runtime/runtime-build.json', 'nro_sha256')
    old_dll = verified(PREVIOUS/'module/libwow64fex.dll', PREVIOUS/'module/build.json', 'sha256')
    old_nro = verified(PREVIOUS/'diagnostic/pes13-fex.nro', PREVIOUS/'diagnostic/runtime-build.json', 'nro_sha256')
    assert interface(dll) == interface(old_dll), 'unexpected PE import/export change'
    assert interface(dll)[0] == 0xaa64
    assert b'[FEX-HOST] ABI 3' in dll and b'[FEX3-HEAP] v8' in dll
    assert b'[FEX3-YIELD] same-core' not in nro
    for name, digest in module['adapter_sources'].items():
        assert sha((ROOT/name).read_bytes()) == digest, name
    assert module['adapter_sources']['src/fex/horizon_host.h'] == runtime['adapter_sources']['horizon_host.h']
    for name, digest in runtime['patch_sources'].items():
        assert sha((ROOT/name).read_bytes()) == digest, name
    assert sha((ROOT/'src/fex/horizon_jit.c').read_bytes()) == runtime['adapter_sources']['horizon_jit.c']
    tests = {}
    for name in ('fast-native', 'abi', 'alloc', 'alias', 'memory', 'code-growth'):
        report = json.loads((WORK/f'{name}-tests.json').read_text())
        assert report['passed'] and report['dll_sha256'] == sha(dll), name
        tests[name] = report
    assert tests['fast-native']['native_elf_sha256'] == runtime['native_elf_sha256']
    native_stress = json.loads((WORK/'native-stress-tests.json').read_text())
    assert native_stress['passed'] and native_stress['host_source_sha256'] == runtime['adapter_sources']['horizon_jit.c']
    config = (ROOT/'config/fex/configuration.ini').read_text().replace('run_guest_tests=1', 'run_guest_tests=0')
    assert config.count('fex_fast=1') == config.count('fex_fastest=0') == 1
    fast_config = config.encode()
    fastest_config = config.replace('fex_fastest=0', 'fex_fastest=1').encode()
    manifest = {
        'source_log_sha256': sha((WORK/'before/fex-runtime.log').read_bytes()),
        'fex_commit': module['fex_commit'], 'host_abi': 3,
        'dll_sha256': sha(dll), 'nro_sha256': sha(nro),
        'native_elf_sha256': runtime['native_elf_sha256'],
        'profiles': {'fast': {'x87_bits': 64, 'scalar_tso': True},
                     'fastest': {'x87_bits': 64, 'scalar_tso': False}},
        'native_private_heap': True, 'samecore_yield': False,
        'hardware_tested': False, 'fps_improvement_measured': False,
        'rollback_dll_sha256': sha(old_dll), 'rollback_nro_sha256': sha(old_nro),
    }
    common = {
        'FEX3-FAST-NATIVE.md': (ROOT/'docs/FEX3-FAST-NATIVE.md').read_bytes(),
        'FEX3-fast-native-manifest.json': (json.dumps(manifest, indent=2)+'\n').encode(),
        'THIRD_PARTY.md': (ROOT/'THIRD_PARTY.md').read_bytes(),
        'licenses/PES13-FEX-adapter-MIT.txt': (ROOT/'src/fex/LICENSE').read_bytes(),
    }
    for path in (WORK/'module/licenses').rglob('*'):
        if path.is_file(): common['licenses/FEX/'+path.relative_to(WORK/'module/licenses').as_posix()] = path.read_bytes()
    for name in (*tests, 'native-stress'):
        common[f'validation/{name}-tests.json'] = (WORK/f'{name}-tests.json').read_bytes()
    results = {}
    for label, ini in (('fast', fast_config), ('fastest', fastest_config)):
        readme = (
            f'PES13-NX FEX3 {label.upper()} + native private heap\n\n'
            'Tutup PES lewat HOME -> X. Copy folder switch dari paket ini ke root SD.\n'
            'Timpa NRO, libwow64fex.dll, dan configuration.ini sebagai satu paket.\n'
            'NRO dan DLL memakai ABI 3; jangan campur dengan runtime lama.\n'
            'Game/save/grafis tidak disertakan. Forwarder tetap switch/pes13-fex/pes13-fex.nro.\n'
            'run_guest_tests=0 sudah diset untuk langsung membuka PES.\n\n'
            'Fast: x87 64-bit, scalar TSO tetap aktif.\n'
            'Fastest: x87 64-bit, scalar TSO nonaktif; dapat menimbulkan error multithreading.\n'
            'Kedua paket memakai binary identik; hanya fex_fastest di INI yang berbeda.\n'
            'Tes Fast dahulu. Simpan lognya, lalu set fex_fastest=1 untuk Fastest.\n'
            'Gunakan clock dan scene yang sama. Kinerja/kelolosan team selection belum teruji di Switch.\n'
            'Lihat FEX3-FAST-NATIVE.md untuk hasil analisa, tes lokal, dan rollback.\n')
        results[label] = archive(f'pes13-fex3-{label}-native',
                                {**common, NRO: nro, DLL: dll, INI: ini, 'README.txt': readme.encode()},
                                {NRO, DLL, INI})
    rollback = {NRO: old_nro, DLL: old_dll,
                'README.txt': b'Restore both files under switch/pes13-fex after HOME -> X.\n'
                              b'This restores alias-perf control ABI 2, not Box64. INI/game/save are unchanged.\n'}
    results['rollback'] = archive('pes13-fex3-fast-native-rollback', rollback, {NRO, DLL})
    result = {'manifest': manifest, 'archives': results}
    (WORK/'package.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
