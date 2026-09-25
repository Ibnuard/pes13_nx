"""Package the native self-suspend fix with verified unchanged ABI-3 DLLs."""
from pathlib import Path
import argparse
import importlib.util
import json

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fex_package_common', ROOT / 'tools/package-fex3-final-3d.py')
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)
sha, read_json, verified, archive = (getattr(common, name) for name in
                                    ('sha', 'read_json', 'verified', 'archive'))
NRO, DLL, NTDLL, INI = common.NRO, common.DLL, common.NTDLL, common.INI
WORK = ROOT / 'local/fex3/self-suspend'
BEFORE = ROOT / 'local/fex3/team-hang'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true',
                        help='Validate archived build inputs without rewriting the tested package')
    args = parser.parse_args()
    module = read_json(WORK / 'module/build.json')
    runtime = read_json(WORK / 'runtime/runtime-build.json')
    patched = read_json(WORK / 'runtime/wine-patches.json')['native-source']
    old_runtime = read_json(BEFORE / 'runtime/runtime-build.json')
    dll = verified(WORK / 'module/libwow64fex.dll', module, 'sha256')
    nro = verified(WORK / 'runtime/pes13-fex.nro', runtime, 'nro_sha256')
    ntdll = verified(WORK / 'runtime/ntdll.dll', runtime, 'ntdll_sha256')
    assert dll == (BEFORE / 'module/libwow64fex.dll').read_bytes()
    assert runtime['native_elf_sha256'] == sha((WORK / 'runtime/wine-nx-runtime.elf').read_bytes())
    for name in ('ntdll_sha256', 'wow64_sha256', 'guest_sha256'):
        assert runtime[name] == old_runtime[name], name
    assert b'pes13-fex3-self-suspend' in nro
    assert b'[FEX3-SELF-WAIT]' in nro and b'[FEX3-HANG-PC]' in nro
    for name, digest in module['adapter_sources'].items():
        assert sha((ROOT / name).read_bytes()) == digest, name
    for name, digest in runtime['adapter_sources'].items():
        assert sha((ROOT / 'src/fex' / name).read_bytes()) == digest, name
    for name, digest in runtime['patch_sources'].items():
        assert sha((ROOT / name).read_bytes()) == digest, name
    assert module['adapter_sources']['src/fex/horizon_host.h'] == runtime['adapter_sources']['horizon_host.h']

    validation = {}
    for name in ('abi', 'alias', 'fast-native', 'code-growth', 'final-3d'):
        path = WORK / f'{name}-tests.json'
        report = read_json(path)
        assert report['passed'] and report['dll_sha256'] == sha(dll), name
        if name == 'fast-native':
            assert report['native_elf_sha256'] == runtime['native_elf_sha256']
        validation[f'validation/{name}-tests.json'] = path.read_bytes()
    for name in ('stall', 'self-suspend', 'self-suspend-binary'):
        path = WORK / f'{name}-tests.json'
        report = read_json(path)
        assert report['passed'], name
        for source, digest in report.get('source_sha256', {}).items():
            assert sha((ROOT / source).read_bytes()) == digest, source
        if name == 'self-suspend':
            assert report['horizon_c_sha256'] == patched['dlls/ntdll/unix/horizon.c']
            assert report['horizon_threads_sha256'] == patched['dlls/ntdll/unix/horizon_threads.h']
        if name == 'self-suspend-binary':
            assert report['native_elf_sha256'] == runtime['native_elf_sha256']
        validation[f'validation/{name}-tests.json'] = path.read_bytes()

    config = (ROOT / 'config/fex/configuration.ini').read_text()
    assert config.count('run_guest_tests=1') == config.count('fex_fastest=0') == 1
    config = config.replace('run_guest_tests=1', 'run_guest_tests=0').replace('fex_fastest=0', 'fex_fastest=1')
    config = config.replace('# Run the test once before switching this experimental package to PES.',
                            '# Self-suspend candidate: restores the pre-team-sync Fastest profile for PES.')
    values = dict(line.split('=', 1) for line in config.splitlines() if line and not line.startswith('#'))
    assert all(values[k] == v for k, v in {'run_guest_tests': '0', 'fex_fast': '1',
                                          'fex_fastest': '1', 'profile': '0', 'production': '1'}.items())
    files = {NRO: nro, DLL: dll, NTDLL: ntdll, INI: config.encode()}
    manifest = {
        'source_log_sha256': sha((WORK / 'before/fex-runtime.log').read_bytes()),
        'fex_commit': module['fex_commit'], 'host_abi': 3,
        'files': {p: sha(data) for p, data in files.items()},
        'validation_sha256': {p: sha(data) for p, data in validation.items()},
        'native_elf_sha256': runtime['native_elf_sha256'],
        'profile': 'fastest, restored to pre-team-sync values',
        'native_self_suspend': 'synchronous reply held until count reaches zero',
        'foreign_running_suspend': 'unsupported', 'suspend_injected_delay_ns': 0,
        'hardware_tested': True, 'hang_fix_confirmed': False, 'fps_improvement_measured': False,
        'hardware_evidence': 'User reports reaching a match, visually around 30 FPS, with minor bugs; no new timing log supplied',
    }
    if args.verify_only:
        print(json.dumps({'verified': True, 'runtime_files': manifest['files'],
                          'native_elf_sha256': manifest['native_elf_sha256'],
                          'validation_reports': len(validation), 'writes': False}, indent=2))
        return
    shared = {
        'FEX3-SELF-SUSPEND.md': (ROOT / 'docs/FEX3-SELF-SUSPEND.md').read_bytes(),
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
        'PES13-NX FEX3 self-suspend\n\n'
        'Tutup PES lewat HOME -> X. Copy seluruh folder switch ke root SD, timpa 4 file.\n'
        'NRO dan INI baru; FEX DLL dan ntdll disertakan agar pasangan lengkap.\n'
        'Forwarder tetap switch/pes13-fex/pes13-fex.nro.\n'
        'Paket langsung membuka PES, Fastest kembali aktif seperti sebelum team-sync.\n'
        'Gunakan INI paket ini: fex_fast=1, fex_fastest=1, profile=0.\n\n'
        'Perbaikan: self-suspend sekarang benar-benar menunggu sampai ResumeThread;\n'
        'bukan mengembalikan NOT_SUPPORTED berulang atau menambahkan delay buatan.\n'
        'Optimasi 2D/heap/cache tetap dipakai. Profil Fastest masih experimental.\n'
        'Tes intro -> Exhibition -> controller -> team selection -> kick-off, clock sama.\n'
        'Jika hang, tunggu 30 detik sebelum HOME -> X, lalu ambil fex-runtime.log.\n'
        'Log harus menunjukkan build pes13-fex3-self-suspend.\n'
        'Build, 1000 siklus pthread, sanitizer dan tes ARM64 lokal lulus.\n'
        'User sudah berhasil masuk match, terlihat sekitar 30 FPS dengan beberapa bug kecil.\n'
        'FPS stabil/terukur belum terkonfirmasi. Dist hanya menyimpan checkpoint terbaru.\n')
    result = {'manifest': manifest, 'archives': {
        'self_suspend': archive('pes13-fex3-self-suspend',
                                {**shared, **validation, **files, 'README.txt': readme.encode()}),
    }}
    (WORK / 'package.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
