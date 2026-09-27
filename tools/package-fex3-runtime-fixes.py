"""Package NRO-only candidate/control overlays, preserving working DLLs/settings."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import zipfile

NRO = 'switch/pes13-fex/pes13-fex.nro'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_overlay(archive, files):
    """Validate archive boundary before creating any output; never overwrite."""
    for name in files:
        path = PurePosixPath(name)
        if (path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name
                or str(path) != name):
            raise ValueError('Unsafe archive path: ' + name)
    if {name for name in files if name.startswith('switch/')} != {NRO}:
        raise ValueError('Overlay may replace only ' + NRO)
    if sum(name.endswith('.nro') for name in files) != 1:
        raise ValueError('Exactly one NRO required')
    archive = Path(archive)
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 27, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None or any(z.read(name) != data for name, data in files.items()):
            raise RuntimeError('Archive readback failed')
    return {'path': str(archive.resolve()), 'sha256': sha(archive.read_bytes()),
            'bytes': archive.stat().st_size, 'files': len(files)}


def load_build(directory, fixes):
    from nro_assets import inspect_nro
    recipe = json.loads((directory / 'runtime-build.json').read_text())
    if recipe.get('runtime_fixes') is not fixes or recipe.get('box64_engine_linked') is not False:
        raise ValueError('Unexpected runtime recipe: ' + str(directory))
    blob = (directory / 'payload/pes13-fex.nro').read_bytes()
    elf = (directory / 'reference/pes13-fex.elf').read_bytes()
    if sha(blob) != recipe['nro_sha256'] or sha(elf) != recipe['native_elf_sha256']:
        raise ValueError('Runtime bytes differ from build receipt')
    project = Path(__file__).resolve().parents[1]
    metadata = inspect_nro(blob, (project / 'assets/icon.jpg').read_bytes(),
                           expected_title='PES13-NX FEX3', expected_version='0.3.0')
    marker = b'pes13-fex3-runtime-fixes' if fixes else b'pes13-fex3-timing-audit'
    if marker not in blob:
        raise ValueError('Missing expected build marker')
    patches = json.loads((directory / 'wine-patches.json').read_text())
    return recipe, patches, blob, metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', required=True, type=Path)
    parser.add_argument('--control', required=True, type=Path)
    parser.add_argument('--validation', required=True, type=Path)
    parser.add_argument('--output-dir', type=Path, default=Path('dist'))
    args = parser.parse_args()
    candidate = load_build(args.candidate, True)
    control = load_build(args.control, False)
    a, ap, _, _ = candidate
    b, bp, _, _ = control
    for key in ('ntdll_sha256', 'wow64_sha256', 'guest_sha256', 'adapter_sources',
                'toolchain_path', 'native_dependencies'):
        if key not in a or a[key] != b.get(key):
            raise ValueError('Control/candidate dependency drift: ' + key)
    if ap['pe-source'] != bp['pe-source']:
        raise ValueError('PE source changed')
    delta = sorted(name for name in ap['native-source'].keys() | bp['native-source'].keys()
                   if ap['native-source'].get(name) != bp['native-source'].get(name))
    if delta != ['dlls/ntdll/unix/horizon.c', 'wine-nx-probe/source/runtime.c']:
        raise ValueError('Unexpected native source delta: ' + repr(delta))
    validation = json.loads(args.validation.read_text())
    if (validation.get('passed') is not True or
            validation.get('candidate_elf_sha256') != a['native_elf_sha256'] or
            validation.get('control_elf_sha256') != b['native_elf_sha256']):
        raise ValueError('Validation does not match candidate/control ELF pair')
    project = Path(__file__).resolve().parents[1]
    outputs = []
    for name, build in (('runtime-fixes', candidate), ('macos-control', control)):
        recipe, patches, blob, metadata = build
        record = {'kind': name, 'target': 'Nintendo Switch / Horizon ARM64',
                  'hardware_tested': False, 'fps_gain_verified': False,
                  'replaces': [NRO], 'requires_existing_fex3_abi': 3,
                  'native_elf_sha256': recipe['native_elf_sha256'],
                  'nro_sha256': recipe['nro_sha256'], 'metadata': metadata,
                  'native_dependencies': recipe['native_dependencies'],
                  'native_source_delta': delta,
                  'validation_sha256': sha(args.validation.read_bytes()),
                  'files': {NRO: sha(blob)}}
        readme = (
            'PES13-NX FEX3 ' + name + ' — NRO-only hardware test\n\n'
            'Target Nintendo Switch, bukan executable macOS.\n'
            '1. Tutup PES lewat HOME lalu X.\n'
            '2. Backup NRO lama switch/pes13-fex/pes13-fex.nro di luar folder switch.\n'
            '3. Salin folder switch dari ZIP ini ke root SD. Hanya satu NRO ditimpa.\n'
            '4. Pakai forwarder dan konfigurasi playable yang sama. Jangan ubah clock\n'
            '   CPU/GPU/RAM, settings.dat, dxvk.conf, preset FEX atau DLL saat membandingkan.\n'
            '5. Simpan fex-runtime.log sesudah tiap run. Ulangi kickoff, restart aplikasi,\n'
            '   lalu ulangi pertandingan yang sama untuk membandingkan cold/warm cache.\n\n'
            'Candidate menambah cache path C:\\dxvk-cache, timer due-time, affinity retry.\n'
            'Kontrol macos-control memakai source timing-audit tanpa tiga backport.\n'
            'Keduanya dibangun ulang dengan toolchain Mac yang sama; kontrol ini BUKAN\n'
            'salinan binary lama yang sudah dimainkan. Rollback persis: pulihkan backup NRO lama.\n'
            'DLL, game, save, profile dan konfigurasi tidak termasuk dan tidak ditimpa.\n'
            'Cache directory baru: switch/pes13-fex/drive_c/dxvk-cache. Jangan hapus\n'
            'cache di antara warm-cache run. Log created/existing belum membuktikan\n'
            'DXVK menulis/membaca cache: periksa cache warning dan file antar-run.\n'
            'Host tests bukan gameplay test; stutter/FPS/simulation speed belum terverifikasi.\n'
        ).encode()
        files = {NRO: blob, 'README.txt': readme,
                 'manifest.json': (json.dumps(record, indent=2) + '\n').encode(),
                 'validation.json': args.validation.read_bytes(),
                 'THIRD_PARTY.md': (project / 'THIRD_PARTY.md').read_bytes(),
                 'licenses/Wine-and-PES13-LGPL-2.1.txt': (project / 'LICENSE').read_bytes(),
                 'licenses/PES13-FEX-adapter-MIT.txt': (project / 'src/fex/LICENSE').read_bytes()}
        for path in (project / 'licenses').rglob('*'):
            if path.is_file() and path.name != 'Box64-LICENSE.txt':
                files[path.relative_to(project).as_posix()] = path.read_bytes()
        outputs.append(write_overlay(args.output_dir / ('pes13-fex3-' + name + '.zip'), files))
    print(json.dumps(outputs, indent=2))


if __name__ == '__main__':
    main()
