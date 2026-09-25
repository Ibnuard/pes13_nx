"""Package the matched final FEX 3D candidate and exact Fastest-native rollback."""
from pathlib import Path
import hashlib
import json
import zipfile

import pefile

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'local/fex3/final-3d'
PREVIOUS = ROOT / 'local/fex3/fast-native'
PREFIX = 'switch/pes13-fex/'
NRO = PREFIX + 'pes13-fex.nro'
DLL = PREFIX + 'drive_c/windows/system32/libwow64fex.dll'
NTDLL = PREFIX + 'drive_c/windows/system32/ntdll.dll'
INI = PREFIX + 'configuration.ini'
SWITCH_PATHS = {NRO, DLL, NTDLL, INI}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text())


def verified(path, report, field):
    data = path.read_bytes()
    assert sha(data) == report[field], path
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


def archive(name, files):
    directory = ROOT / 'dist' / name
    assert directory.resolve().is_relative_to((ROOT / 'dist').resolve())
    existing = {p.relative_to(directory).as_posix()
                for p in directory.rglob('*') if p.is_file()}
    assert existing <= set(files), f'Unexpected old files in {directory}: {existing - set(files)}'
    for relative, data in files.items():
        path = directory / relative
        assert path.resolve().is_relative_to(directory.resolve())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    target = directory.with_suffix('.zip')
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as output:
        for relative, data in sorted(files.items()):
            entry = zipfile.ZipInfo(relative, (2026, 9, 25, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            output.writestr(entry, data)
    with zipfile.ZipFile(target) as check:
        assert check.testzip() is None and set(check.namelist()) == set(files)
        assert {p for p in check.namelist() if p.startswith('switch/')} == SWITCH_PATHS
        for path, data in files.items():
            assert check.read(path) == data
    return {'zip': str(target), 'directory': str(directory),
            'sha256': sha(target.read_bytes()), 'bytes': target.stat().st_size}


def main():
    module = read_json(WORK / 'module/build.json')
    runtime = read_json(WORK / 'runtime/runtime-build.json')
    before = read_json(WORK / 'before/runtime-build.json')
    old_module = read_json(PREVIOUS / 'module/build.json')
    dll = verified(WORK / 'module/libwow64fex.dll', module, 'sha256')
    nro = verified(WORK / 'runtime/pes13-fex.nro', runtime, 'nro_sha256')
    ntdll = verified(WORK / 'runtime/ntdll.dll', runtime, 'ntdll_sha256')
    old_dll = verified(PREVIOUS / 'module/libwow64fex.dll', old_module, 'sha256')
    old_nro = verified(PREVIOUS / 'runtime/pes13-fex.nro', before, 'nro_sha256')
    old_ntdll = verified(WORK / 'before/ntdll.dll', before, 'ntdll_sha256')
    for current, previous in ((dll, old_dll), (ntdll, old_ntdll)):
        assert interface(current) == interface(previous), 'Unexpected PE interface change'
        assert interface(current)[0] == 0xaa64
    assert b'[FEX-HOST] ABI 3' in dll and b'[FEX3-SMC] v2' in dll
    assert b'pes13-fex3-final-3d' in nro and b'[FEX3-SUSPEND]' in nro
    assert runtime['wow64_sha256'] == before['wow64_sha256'], 'wow64.dll must be packaged if changed'
    assert runtime['guest_sha256'] == before['guest_sha256'], 'Guest test must be packaged if changed'
    for name, digest in module['adapter_sources'].items():
        assert sha((ROOT / name).read_bytes()) == digest, name
    for name, digest in runtime['patch_sources'].items():
        assert sha((ROOT / name).read_bytes()) == digest, name
    for name, digest in runtime['adapter_sources'].items():
        assert sha((ROOT / 'src/fex' / name).read_bytes()) == digest, name
    assert module['adapter_sources']['src/fex/horizon_host.h'] == runtime['adapter_sources']['horizon_host.h']

    tests = {}
    validation = {}
    for name in ('abi', 'alias', 'code-growth', 'fast-native', 'smc', 'final-3d'):
        path = WORK / f'{name}-tests.json'
        report = read_json(path)
        assert report['passed'] and report['dll_sha256'] == sha(dll), name
        tests[name] = report
        validation[f'validation/{name}-tests.json'] = path.read_bytes()
    assert tests['fast-native']['native_elf_sha256'] == runtime['native_elf_sha256']
    assert tests['final-3d']['before_sha256'] == sha(old_dll)
    suspend = read_json(WORK / 'suspend-tests.json')
    assert suspend['passed'] and suspend['ntdll_sha256'] == sha(ntdll)
    assert suspend['before']['ntdll_sha256'] == sha(old_ntdll)
    validation['validation/suspend-tests.json'] = (WORK / 'suspend-tests.json').read_bytes()
    # Reuse sanitizer evidence only for the byte-identical native heap source.
    native_stress = read_json(PREVIOUS / 'native-stress-tests.json')
    assert native_stress['passed'] and native_stress['host_source_sha256'] == runtime['adapter_sources']['horizon_jit.c']
    assert native_stress['test_source_sha256'] == sha((ROOT / 'tests/fex_heap_native.c').read_bytes())
    validation['validation/native-stress-unchanged-source.json'] = (PREVIOUS / 'native-stress-tests.json').read_bytes()

    config = (ROOT / 'config/fex/configuration.ini').read_text()
    assert config.count('run_guest_tests=1') == config.count('fex_fastest=0') == 1
    config = config.replace('run_guest_tests=1', 'run_guest_tests=0').replace('fex_fastest=0', 'fex_fastest=1')
    config = config.replace('# Run the test once before switching this experimental package to PES.',
                            '# Final 3D candidate: launches PES directly; see FEX3-FINAL-3D.md.')
    values = dict(line.split('=', 1) for line in config.splitlines() if line and not line.startswith('#'))
    assert all(values[key] == value for key, value in
               {'run_guest_tests': '0', 'fex_fast': '1', 'fex_fastest': '1',
                'production': '1', 'profile': '0'}.items())
    old_config_path = ROOT / 'dist/pes13-fex3-fastest-native' / INI
    old_config = old_config_path.read_bytes()
    old_package = ROOT / 'dist/pes13-fex3-fastest-native.zip'
    with zipfile.ZipFile(old_package) as old_zip:
        assert old_zip.read(INI) == old_config
        assert old_zip.read(DLL) == old_dll and old_zip.read(NRO) == old_nro

    runtime_files = {NRO: nro, DLL: dll, NTDLL: ntdll, INI: config.encode()}
    rollback_files = {NRO: old_nro, DLL: old_dll, NTDLL: old_ntdll, INI: old_config}
    manifest = {
        'source_log_sha256': sha((WORK / 'before/fex-runtime.log').read_bytes()),
        'fex_commit': module['fex_commit'], 'host_abi': 3,
        'files': {p: sha(b) for p, b in runtime_files.items()},
        'rollback_files': {p: sha(b) for p, b in rollback_files.items()},
        'validation_sha256': {p: sha(b) for p, b in validation.items()},
        'native_elf_sha256': runtime['native_elf_sha256'],
        'profile': 'fastest', 'suspend_injected_delay_ns': 0,
        'entry_smc_images': ['pes2013.exe', 'd3d9.dll'],
        'entry_smc_section': 'read-only executable .text',
        'optional_early_jit_spare_mib': 128,
        'hardware_tested': False, 'fps_improvement_measured': False,
        'rollback_target': 'previous Fastest-native ABI 3, not Box64',
    }
    common = {
        'FEX3-FINAL-3D.md': (ROOT / 'docs/FEX3-FINAL-3D.md').read_bytes(),
        'FEX3-final-3d-manifest.json': (json.dumps(manifest, indent=2) + '\n').encode(),
        'THIRD_PARTY.md': (ROOT / 'THIRD_PARTY.md').read_bytes(),
        'licenses/Wine-LGPL-2.1.txt': (ROOT / 'LICENSE').read_bytes(),
        'licenses/PES13-FEX-adapter-MIT.txt': (ROOT / 'src/fex/LICENSE').read_bytes(),
        'licenses/libnx-ISC.txt': (ROOT / 'src/fex/libnx-LICENSE').read_bytes(),
    }
    for path in (WORK / 'module/licenses').rglob('*'):
        if path.is_file():
            common['licenses/FEX/' + path.relative_to(WORK / 'module/licenses').as_posix()] = path.read_bytes()
    readme = (
        'PES13-NX FEX3 - final 3D candidate\n\n'
        'Tutup PES lewat HOME -> X. Copy seluruh folder switch dari paket ini ke root SD.\n'
        'Timpa empat file: pes13-fex.nro, configuration.ini, libwow64fex.dll dan ntdll.dll.\n'
        'Jangan hanya copy NRO: penghapusan jeda suspend berada di ntdll.dll ARM64.\n'
        'Forwarder tetap switch/pes13-fex/pes13-fex.nro. Game, save, dan grafis tetap.\n'
        'PES langsung dibuka: run_guest_tests=0, fex_fast=1, fex_fastest=1.\n\n'
        'Tes dengan clock dan scene yang sama. Target tes: team selection lalu kick-off.\n'
        'Lanjutkan melalui replay/corner bila berhasil. Simpan fex-runtime.log setelah tes.\n'
        'Perubahan: hapus jeda suspend 1ms, betulkan interval kode RX, periksa blok statis\n'
        'saat entry, dan cadangkan satu cache JIT 128 MiB lebih awal.\n'
        'Profil agresif ini masih experimental: memori ordering dilonggarkan dan pemeriksaan\n'
        'kode statis dilakukan per entry. Lihat dokumen untuk batas kompatibilitas.\n'
        'Build dan tes lokal lulus; belum membuktikan FPS atau kick-off di Switch.\n\n'
        'Rollback FEX tersedia terpisah: pes13-fex3-final-3d-rollback.zip.\n'
        'Jika kesempatan terakhir ini gagal, lanjutkan kembali backend Box64.\n')
    results = {
        'final_3d': archive('pes13-fex3-final-3d',
                            {**common, **validation, **runtime_files, 'README.txt': readme.encode()}),
        'rollback': archive('pes13-fex3-final-3d-rollback', {
            **common, **rollback_files,
            'README.txt': (
                'PES13-NX FEX3 rollback ke Fastest-native sebelumnya (ABI 3).\n'
                'Tutup aplikasi HOME -> X. Copy seluruh folder switch ke root SD, timpa 4 file.\n'
                'NRO, libwow64fex.dll, ntdll.dll, dan INI semuanya dikembalikan sebagai pasangan.\n'
                'Ini rollback FEX sebelumnya, BUKAN paket Box64. Game/save tetap.\n').encode(),
        }),
    }
    result = {'manifest': manifest, 'archives': results}
    (WORK / 'package.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
