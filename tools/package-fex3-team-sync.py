"""Package the ordering candidate, bounded observer, and exact final-3d rollback."""
from pathlib import Path
import importlib.util
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fex_package_common', ROOT / 'tools/package-fex3-final-3d.py')
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)
sha, read_json, verified, interface, archive = (getattr(common, name) for name in
                                               ('sha', 'read_json', 'verified', 'interface', 'archive'))
NRO, DLL, NTDLL, INI = common.NRO, common.DLL, common.NTDLL, common.INI
WORK = ROOT / 'local/fex3/team-hang'
BEFORE = ROOT / 'local/fex3/final-3d'


def main():
    module = read_json(WORK / 'module/build.json')
    runtime = read_json(WORK / 'runtime/runtime-build.json')
    dll = verified(WORK / 'module/libwow64fex.dll', module, 'sha256')
    nro = verified(WORK / 'runtime/pes13-fex.nro', runtime, 'nro_sha256')
    ntdll = verified(WORK / 'runtime/ntdll.dll', runtime, 'ntdll_sha256')
    old_runtime = read_json(BEFORE / 'runtime/runtime-build.json')
    old_module = read_json(BEFORE / 'module/build.json')
    assert interface(dll) == interface((BEFORE / 'module/libwow64fex.dll').read_bytes())
    assert runtime['ntdll_sha256'] == old_runtime['ntdll_sha256']
    assert runtime['wow64_sha256'] == old_runtime['wow64_sha256']
    assert runtime['guest_sha256'] == old_runtime['guest_sha256']
    assert b'pes13-fex3-team-sync' in nro and b'[FEX3-HANG-PC]' in nro
    assert b'[FEX3-SUSPEND-RESULT]' in nro
    assert b'fast x87=64 scalar_tso=1 vector_tso=1 memcpy_tso=1' in dll
    for name, digest in module['adapter_sources'].items():
        assert sha((ROOT / name).read_bytes()) == digest, name
    for name, digest in runtime['adapter_sources'].items():
        assert sha((ROOT / 'src/fex' / name).read_bytes()) == digest, name
    for name, digest in runtime['patch_sources'].items():
        assert sha((ROOT / name).read_bytes()) == digest, name
    assert module['adapter_sources']['src/fex/horizon_host.h'] == runtime['adapter_sources']['horizon_host.h']
    assert module['adapter_sources']['src/fex/horizon_stall.h'] == runtime['adapter_sources']['horizon_stall.h']

    evidence = {}
    for name in ('abi', 'alias', 'fast-native', 'code-growth', 'final-3d'):
        path = WORK / f'{name}-tests.json'
        report = read_json(path)
        assert report['passed'] and report['dll_sha256'] == sha(dll), name
        if name == 'fast-native':
            assert report['native_elf_sha256'] == runtime['native_elf_sha256']
        evidence[f'validation/{name}-tests.json'] = path.read_bytes()
    stall = read_json(WORK / 'stall-tests.json')
    assert stall['passed']
    for name, digest in stall['source_sha256'].items():
        assert sha((ROOT / name).read_bytes()) == digest, name
    evidence['validation/stall-tests.json'] = (WORK / 'stall-tests.json').read_bytes()

    config = (ROOT / 'config/fex/configuration.ini').read_text()
    assert config.count('run_guest_tests=1') == config.count('fex_fastest=0') == 1
    config = config.replace('run_guest_tests=1', 'run_guest_tests=0')
    config = config.replace('# Run the test once before switching this experimental package to PES.',
                            '# Team-sync: launches PES with ordered Fast; keep fex_fastest=0 for this test.')
    values = dict(line.split('=', 1) for line in config.splitlines() if line and not line.startswith('#'))
    assert all(values[k] == v for k, v in {'run_guest_tests': '0', 'fex_fast': '1',
                                          'fex_fastest': '0', 'profile': '0', 'production': '1'}.items())
    files = {NRO: nro, DLL: dll, NTDLL: ntdll, INI: config.encode()}
    with zipfile.ZipFile(ROOT / 'dist/pes13-fex3-final-3d.zip') as previous:
        rollback = {name: previous.read(name) for name in common.SWITCH_PATHS}
    assert sha(rollback[NRO]) == old_runtime['nro_sha256']
    assert sha(rollback[DLL]) == old_module['sha256']
    assert rollback[NTDLL] == ntdll
    manifest = {
        'source_log_sha256': sha((WORK / 'before/fex-runtime.log').read_bytes()),
        'fex_commit': module['fex_commit'], 'host_abi': 3,
        'files': {p: sha(data) for p, data in files.items()},
        'rollback_files': {p: sha(data) for p, data in rollback.items()},
        'validation_sha256': {p: sha(data) for p, data in evidence.items()},
        'native_elf_sha256': runtime['native_elf_sha256'],
        'profile': {'name': 'fast', 'x87_bits': 64, 'scalar_tso': True,
                    'vector_tso': True, 'memcpy_tso': True},
        'stall_capture_maximum': 3, 'stall_threshold_seconds': 10,
        'continuous_sampler': False,
        'hardware_tested': False, 'hang_fix_confirmed': False,
        'fps_improvement_measured': False, 'rollback_target': 'final-3d Fastest, not Box64',
    }
    shared = {
        'FEX3-TEAM-SYNC.md': (ROOT / 'docs/FEX3-TEAM-SYNC.md').read_bytes(),
        'manifest.json': (json.dumps(manifest, indent=2) + '\n').encode(),
        'THIRD_PARTY.md': (ROOT / 'THIRD_PARTY.md').read_bytes(),
        'licenses/Wine-LGPL-2.1.txt': (ROOT / 'LICENSE').read_bytes(),
        'licenses/PES13-FEX-adapter-MIT.txt': (ROOT / 'src/fex/LICENSE').read_bytes(),
        'licenses/libnx-ISC.txt': (ROOT / 'src/fex/libnx-LICENSE').read_bytes(),
    }
    for path in (WORK / 'module/licenses').rglob('*'):
        if path.is_file():
            shared['licenses/FEX/' + path.relative_to(WORK / 'module/licenses').as_posix()] = path.read_bytes()
    readme = (
        'PES13-NX FEX3 team-sync\n\n'
        'Tutup PES lewat HOME -> X. Copy seluruh folder switch ke root SD dan timpa 4 file.\n'
        'Termasuk pes13-fex.nro, libwow64fex.dll, ntdll.dll dan configuration.ini.\n'
        'Forwarder tetap switch/pes13-fex/pes13-fex.nro. Game/save tidak disertakan.\n'
        'Paket langsung membuka PES dengan Fast + scalar/SIMD/string TSO aktif.\n'
        'Pertahankan fex_fastest=0; mengaktifkannya mematikan perubahan ordering ini.\n'
        'Optimasi proteksi memori, heap dan cache final-3d tetap dipakai.\n\n'
        'Tes dengan clock yang sama: Exhibition -> controller -> team selection -> kick-off.\n'
        'Jika hang, tunggu 20-30 detik sebelum HOME -> X, lalu ambil fex-runtime.log.\n'
        'Snapshot otomatis hanya aktif setelah present berhenti 10 detik, maksimal 3 kali.\n'
        'Tidak perlu mengaktifkan profile/verbose atau menambah file TXT.\n'
        'Log wajib menunjukkan build pes13-fex3-team-sync dan TSO 1/1/1.\n'
        'Build dan tes lokal lulus; penyebab hang dan perbaikan di Switch belum terbukti.\n'
        'Rollback terpisah mengembalikan final-3d, bukan Box64.\n')
    results = {
        'team_sync': archive('pes13-fex3-team-sync',
                             {**shared, **evidence, **files, 'README.txt': readme.encode()}),
        'rollback': archive('pes13-fex3-team-sync-rollback', {
            **shared, **rollback, 'README.txt': (
                'Restore exact FEX3 final-3d NRO/DLL/ntdll/INI after HOME -> X.\n'
                'Copy the entire switch folder to SD root and overwrite.\n'
                'This restores the previous Fastest candidate, not Box64.\n').encode(),
        }),
    }
    output = {'manifest': manifest, 'archives': results}
    (WORK / 'package.json').write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
