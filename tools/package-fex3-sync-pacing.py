"""Package the pacing candidate as a verified copy-ready directory, without ZIP."""
from pathlib import Path
import argparse
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'local/fex3/sync-pacing'
BASE = ROOT / 'local/fex3/self-suspend'
PREFIX = 'switch/pes13-fex/'
DEST = ROOT / 'dist/pes13-fex3-sync-pacing'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text())


def checked(path, digest):
    data = path.read_bytes()
    assert sha(data) == digest, path
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recovery', action='store_true',
                        help='Package shared-wakeup recovery after the sync-pacing device regression')
    recovery = parser.parse_args().recovery
    suffix = 'sync-recovery' if recovery else 'sync-pacing'
    build_name = 'pes13-fex3-' + suffix
    WORK = ROOT / 'local/fex3' / suffix
    DEST = ROOT / 'dist' / build_name
    runtime = read_json(WORK / 'runtime/runtime-build.json')
    patched = read_json(WORK / 'runtime/wine-patches.json')['native-source']
    module = read_json(BASE / 'module/build.json')
    before = read_json(BASE / 'runtime/runtime-build.json')
    checkpoint = read_json(BASE / 'package.json')
    checked(WORK / 'runtime/wine-nx-runtime.elf', runtime['native_elf_sha256'])
    for key in ('ntdll_sha256', 'wow64_sha256', 'guest_sha256'):
        assert runtime[key] == before[key], key
    for name, digest in runtime['patch_sources'].items():
        checked(ROOT / name, digest)
    for name, digest in runtime['adapter_sources'].items():
        checked(ROOT / 'src/fex' / name, digest)
    for name, digest in module['adapter_sources'].items():
        checked(ROOT / name, digest)
    assert module['adapter_sources']['src/fex/horizon_host.h'] == runtime['adapter_sources']['horizon_host.h']

    # Preserve the exact successful checkpoint, including its original ZIP.
    for name, digest in checkpoint['manifest']['files'].items():
        checked(ROOT / 'dist/pes13-fex3-self-suspend' / name, digest)
    checked(ROOT / 'dist/pes13-fex3-self-suspend.zip',
            checkpoint['archives']['self_suspend']['sha256'])
    prior = ROOT / 'dist/pes13-fex3-kickoff-pacing'
    for name, digest in read_json(prior / 'manifest.json')['files'].items():
        checked(prior / name, digest)
    if recovery:
        regression = ROOT / 'dist/pes13-fex3-sync-pacing'
        for name, digest in read_json(regression / 'manifest.json')['files'].items():
            checked(regression / name, digest)
    nro = checked(WORK / 'runtime/pes13-fex.nro', runtime['nro_sha256'])
    assert build_name.encode() in nro and b'[FEX3-PACE]' in nro
    assert b'[FEX3-PIPE]' in nro and b'[FEX3-SYNC]' in nro and b'[FEX3-DELAY]' in nro
    assert b'[FEX3-SELF-WAIT]' in nro and b'DXVK_CONFIG_FILE=C:\\PES13\\dxvk.conf\0' in nro
    ini = checked(ROOT / 'dist/pes13-fex3-self-suspend' / (PREFIX + 'configuration.ini'),
                  checkpoint['manifest']['files'][PREFIX + 'configuration.ini'])
    ini += (b'\n# Recovery: original shared wakeups, bypass the experimental router.\nfex_targeted_wake=0\n'
            if recovery else b'\n# FEX server: targeted object notifications; 0 restores shared broadcasts.\nfex_targeted_wake=1\n')
    dxvk = (ROOT / 'config/fex/dxvk-low-latency.conf').read_bytes()
    values = dict(line.split('=', 1) for line in dxvk.decode().splitlines()
                  if line and not line.startswith('#'))
    assert {k.strip(): v.strip() for k, v in values.items()} == {'d3d9.maxFrameRate': '-1', 'd3d9.maxFrameLatency': '1'}
    files = {
        PREFIX + 'pes13-fex.nro': nro,
        PREFIX + 'drive_c/windows/system32/libwow64fex.dll': checked(BASE / 'module/libwow64fex.dll', module['sha256']),
        PREFIX + 'drive_c/windows/system32/ntdll.dll': checked(WORK / 'runtime/ntdll.dll', runtime['ntdll_sha256']),
        PREFIX + 'configuration.ini': ini,
        PREFIX + 'drive_c/PES13/dxvk.conf': dxvk,
    }
    validation = {}
    for name in ('frame', 'pipeline', 'pipeline-binary', 'self-suspend-binary', 'fast-native', 'sync', 'sync-binary'):
        data = (WORK / f'{name}-tests.json').read_bytes()
        report = json.loads(data)
        assert report['passed'], name
        if name == 'frame':
            assert report['runtime_c_sha256'] == patched['wine-nx-probe/source/runtime.c']
            assert report['vulkan_c_sha256'] == patched['dlls/win32u/vulkan.c']
        elif name in ('pipeline', 'sync'):
            for path, digest in report['patched_source_sha256'].items():
                assert patched[path] == digest, path
        else:
            assert report['native_elf_sha256'] == runtime['native_elf_sha256']
        for path, digest in report.get('source_sha256', {}).items():
            checked(ROOT / path, digest)
        if name == 'fast-native':
            assert report['dll_sha256'] == module['sha256']
        validation[f'validation/{name}-tests.json'] = data
    manifest = {
        'build': build_name, 'host_abi': 3,
        'fex_commit': module['fex_commit'], 'hardware_tested': False,
        'files': {name: sha(data) for name, data in files.items()},
        'input_log_sha256': sha((ROOT / 'local/fex3' /
                                ('sync-result' if recovery else 'kickoff-result') / 'fex-runtime.log').read_bytes()),
        'native_elf_sha256': runtime['native_elf_sha256'],
        'validation_sha256': {name: sha(data) for name, data in validation.items()},
        'profile': 'checkpoint Fastest, unchanged', 'dxvk_max_frame_rate': -1, 'dxvk_max_frame_latency': 1,
        'guest_clock_scaled': False, 'targeted_wake': not recovery, 'zip_created': False,
        'source_checkpoint': '38a6d0c211b9aca8edd2bd60f488f668a17fc012',
        'checkpoint_preserved': True,
    }
    files.update(validation)
    files.update({
        'manifest.json': (json.dumps(manifest, indent=2) + '\n').encode(),
        ('FEX3-SYNC-RECOVERY.md' if recovery else 'FEX3-SYNC-PACING.md'):
            (ROOT / 'docs' / ('FEX3-SYNC-RECOVERY.md' if recovery else 'FEX3-SYNC-PACING.md')).read_bytes(),
        'THIRD_PARTY.md': (ROOT / 'THIRD_PARTY.md').read_bytes(),
        'licenses/Wine-LGPL-2.1.txt': (ROOT / 'LICENSE').read_bytes(),
        'licenses/PES13-FEX-adapter-MIT.txt': (ROOT / 'src/fex/LICENSE').read_bytes(),
        'licenses/libnx-ISC.txt': (ROOT / 'src/fex/libnx-LICENSE').read_bytes(),
        'README.txt': (
            'PES13-NX FEX3 sync pacing (folder only; no ZIP)\n\n'
            'Tutup PES lewat HOME -> X. Copy folder switch ke root SD dan timpa 5 file.\n'
            'Forwarder: switch/pes13-fex/pes13-fex.nro. Game dan save memakai instalasi existing.\n'
            'Perubahan: event/mutex/semaphore membangunkan select waiter yang relevan.\n'
            'Self-suspend/start tetap memakai shared gate; timeout/status tetap asli.\n'
            'FEX Fastest, clocks game, DXVK DLL dan maxFrameLatency=1 tetap sama.\n'
            'Tambahan log tiap 10 detik: FEX3-SYNC dan FEX3-DELAY. Tanpa I/O per frame.\n\n'
            'Tes kick-off, scoreboard, umpan cepat, set piece/replay, lalu gameplay beberapa menit.\n'
            'Jaga clock tetap sepanjang run. Tes stock pada run terpisah dari awal aplikasi.\n'
            'Log harus menunjukkan build pes13-fex3-sync-pacing dan startup targeted=1.\n'
            'Simpan fex-runtime.log dan catat waktu pause/loncat.\n\n'
            'Control opsional: set fex_targeted_wake=0 dalam configuration.ini, lalu restart.\n'
            'Itu mengembalikan broadcast lama pada NRO yang sama; restore 1 untuk optimasi.\n'
            'Build dan tes lokal lulus; hasil FPS/pacing di Switch belum terverifikasi.\n'
        ).encode(),
    })
    if recovery:
        files['README.txt'] = (
            'PES13-NX FEX3 sync recovery (folder only; no ZIP)\n\n'
            'Tutup PES lewat HOME -> X. Copy folder switch ke root SD dan timpa 5 file.\n'
            'Forwarder tetap: switch/pes13-fex/pes13-fex.nro.\n'
            'WAJIB timpa configuration.ini juga: fex_targeted_wake=0.\n\n'
            'Runtime kembali memakai shared wakeup sebelum sync-pacing.\n'
            'Mode 0 sekarang melewati parsing, daftar waiter, lookup dan statistik router.\n'
            'Self-suspend, FEX Fastest, clock game dan konfigurasi DXVK tetap sama.\n'
            'Log Sleep/yield dipertahankan untuk membandingkan jeda thread.\n\n'
            'Periksa build pes13-fex3-sync-recovery dan startup targeted=0.\n'
            'Tes dengan clock yang sama sepanjang run: menu -> team select -> kick-off.\n'
            'Jika lolos, lanjutkan beberapa menit dengan umpan cepat dan replay.\n'
            'Simpan fex-runtime.log sebelum membuka aplikasi lagi.\n'
            'Jangan aktifkan targeted wake pada pengujian pemulihan ini.\n\n'
            'Build dan tes lokal lulus. Pemulihan hang/performa belum teruji di Switch.\n'
        ).encode()
        files['analysis.json'] = (ROOT / 'local/fex3/sync-result/analysis.json').read_bytes()
    for path in (BASE / 'module/licenses').rglob('*'):
        if path.is_file():
            files['licenses/FEX/' + path.relative_to(BASE / 'module/licenses').as_posix()] = path.read_bytes()
    assert DEST.resolve().is_relative_to((ROOT / 'dist').resolve())
    assert not DEST.with_suffix('.zip').exists(), 'No ZIP belongs to this candidate'
    existing = {p.relative_to(DEST).as_posix() for p in DEST.rglob('*') if p.is_file()}
    assert existing <= set(files), 'Preserving unexpected destination files'
    for name, data in files.items():
        path = DEST / name
        assert path.resolve().is_relative_to(DEST.resolve())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        assert path.read_bytes() == data
    assert sum(p.endswith('.nro') for p in files) == 1
    assert {p for p in files if p.startswith('switch/')} == set(manifest['files'])
    result = {'directory': str(DEST), 'zip_created': False, 'manifest': manifest}
    (WORK / 'package.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
