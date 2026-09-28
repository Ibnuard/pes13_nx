"""Package the pacing candidate as a verified copy-ready directory, without ZIP."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'local/fex3/frame-pacing'
BASE = ROOT / 'local/fex3/self-suspend'
PREFIX = 'switch/pes13-fex/'
DEST = ROOT / 'dist/pes13-fex3-frame-pacing'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text())


def checked(path, digest):
    data = path.read_bytes()
    assert sha(data) == digest, path
    return data


def main():
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
    nro = checked(WORK / 'runtime/pes13-fex.nro', runtime['nro_sha256'])
    assert b'pes13-fex3-frame-pacing' in nro and b'[FEX3-PACE]' in nro
    assert b'[FEX3-SELF-WAIT]' in nro and b'DXVK_CONFIG_FILE=C:\\PES13\\dxvk.conf\0' in nro
    ini = checked(ROOT / 'dist/pes13-fex3-self-suspend' / (PREFIX + 'configuration.ini'),
                  checkpoint['manifest']['files'][PREFIX + 'configuration.ini'])
    dxvk = (ROOT / 'config/fex/dxvk.conf').read_bytes()
    values = dict(line.split('=', 1) for line in dxvk.decode().splitlines()
                  if line and not line.startswith('#'))
    assert {k.strip(): v.strip() for k, v in values.items()} == {'d3d9.maxFrameRate': '-1'}
    files = {
        PREFIX + 'pes13-fex.nro': nro,
        PREFIX + 'drive_c/windows/system32/libwow64fex.dll': checked(BASE / 'module/libwow64fex.dll', module['sha256']),
        PREFIX + 'drive_c/windows/system32/ntdll.dll': checked(WORK / 'runtime/ntdll.dll', runtime['ntdll_sha256']),
        PREFIX + 'configuration.ini': ini,
        PREFIX + 'drive_c/PES13/dxvk.conf': dxvk,
    }
    validation = {}
    for name in ('frame', 'self-suspend-binary', 'fast-native'):
        data = (WORK / f'{name}-tests.json').read_bytes()
        report = json.loads(data)
        assert report['passed'], name
        if name == 'frame':
            assert report['runtime_c_sha256'] == patched['wine-nx-probe/source/runtime.c']
            assert report['vulkan_c_sha256'] == patched['dlls/win32u/vulkan.c']
        else:
            assert report['native_elf_sha256'] == runtime['native_elf_sha256']
        for path, digest in report.get('source_sha256', {}).items():
            checked(ROOT / path, digest)
        if name == 'fast-native':
            assert report['dll_sha256'] == module['sha256']
        validation[f'validation/{name}-tests.json'] = data
    manifest = {
        'build': 'pes13-fex3-frame-pacing', 'host_abi': 3,
        'fex_commit': module['fex_commit'], 'hardware_tested': False,
        'files': {name: sha(data) for name, data in files.items()},
        'input_log_sha256': sha((WORK / 'before/fex-runtime.log').read_bytes()),
        'native_elf_sha256': runtime['native_elf_sha256'],
        'validation_sha256': {name: sha(data) for name, data in validation.items()},
        'profile': 'checkpoint Fastest, unchanged', 'dxvk_max_frame_rate': -1,
        'guest_clock_scaled': False, 'zip_created': False,
        'source_checkpoint': '38a6d0c211b9aca8edd2bd60f488f668a17fc012',
        'checkpoint_preserved': True,
    }
    files.update(validation)
    files.update({
        'manifest.json': (json.dumps(manifest, indent=2) + '\n').encode(),
        'FEX3-FRAME-PACING.md': (ROOT / 'docs/FEX3-FRAME-PACING.md').read_bytes(),
        'THIRD_PARTY.md': (ROOT / 'THIRD_PARTY.md').read_bytes(),
        'licenses/Wine-LGPL-2.1.txt': (ROOT / 'LICENSE').read_bytes(),
        'licenses/PES13-FEX-adapter-MIT.txt': (ROOT / 'src/fex/LICENSE').read_bytes(),
        'licenses/libnx-ISC.txt': (ROOT / 'src/fex/libnx-LICENSE').read_bytes(),
        'README.txt': (
            'PES13-NX FEX3 frame-pacing candidate (folder only; no ZIP)\n\n'
            'Tutup PES lewat HOME -> X. Copy folder switch ke root SD dan timpa 5 file.\n'
            'Forwarder tetap switch/pes13-fex/pes13-fex.nro. Game dan save tetap memakai instalasi kamu.\n'
            'Fastest dan DLL sama dengan checkpoint self-suspend yang sudah berhasil masuk match.\n'
            'DXVK automatic software limiter dimatikan; sinkronisasi FIFO tetap mengikuti game.\n'
            'Tidak ada perubahan kecepatan waktu game atau delay tambahan suspend.\n'
            'NRO menambah ringkasan frame-time tiap sekitar 10 detik, tanpa tulis SD per frame.\n\n'
            'Tes kick-off 5 menit dengan clock sama, umpan cepat/corner/replay, lalu simpan fex-runtime.log.\n'
            'Harus ada build pes13-fex3-frame-pacing dan DXVK d3d9.maxFrameRate = -1.\n'
            'Jika terus terlalu cepat, ubah drive_c/PES13/dxvk.conf: d3d9.maxFrameRate = 0, lalu restart.\n'
            'Itu control limiter lama dengan NRO yang sama. Catat setting yang dipakai saat kirim log.\n'
            'Build dan tes lokal lulus; perbaikan stutter/FPS masih perlu dibuktikan di Switch.\n'
        ).encode(),
    })
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
