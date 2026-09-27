"""Package read-only FEX3 diagnostic as a verified NRO-only Switch overlay."""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import zipfile

from nro_assets import inspect_nro

NRO = 'switch/pes13-fex/pes13-fex.nro'
ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(directory, marker):
    receipt = json.loads((directory / 'runtime-build.json').read_text())
    patches = json.loads((directory / 'wine-patches.json').read_text())
    nro = (directory / 'payload/pes13-fex.nro').read_bytes()
    elf = (directory / 'reference/pes13-fex.elf').read_bytes()
    if sha(nro) != receipt['nro_sha256'] or sha(elf) != receipt['native_elf_sha256']:
        raise ValueError('Build receipt does not match binary bytes')
    if elf[:4] != b'\x7fELF' or struct.unpack_from('<H', elf, 18)[0] != 183:
        raise ValueError('Expected Horizon ARM64 ELF')
    if marker.encode() not in nro:
        raise ValueError('Missing diagnostic/control build marker')
    metadata = inspect_nro(nro, (ROOT / 'assets/icon.jpg').read_bytes(),
                           expected_title='PES13-NX FEX3', expected_version='0.3.0')
    return receipt, patches, nro, metadata


def package(control_dir, diagnostic_dir, destination):
    control, cp, control_nro, _ = load(Path(control_dir), 'pes13-fex3-timing-audit')
    diagnostic, dp, blob, metadata = load(Path(diagnostic_dir), 'pes13-fex3-event-diagnostic')
    if control.get('runtime_fixes') is not False or diagnostic.get('runtime_fixes') is not False \
            or diagnostic.get('diagnostic') is not True:
        raise ValueError('Diagnostic must use unmodified runtime-fixes control')
    for key in ('ntdll_sha256', 'wow64_sha256', 'guest_sha256', 'adapter_sources',
                'toolchain_path', 'native_dependencies'):
        if diagnostic.get(key) != control.get(key) or key not in diagnostic:
            raise ValueError('Control/diagnostic ABI drift: ' + key)
    if cp['pe-source'] != dp['pe-source']:
        raise ValueError('PE source drift')
    delta = sorted(name for name in cp['native-source'].keys() | dp['native-source'].keys()
                   if cp['native-source'].get(name) != dp['native-source'].get(name))
    if delta != ['wine-nx-probe/source/runtime.c']:
        raise ValueError('Unexpected native source changes: ' + repr(delta))
    for path, digest in diagnostic['patch_sources'].items():
        if sha((ROOT / path).read_bytes()) != digest:
            raise ValueError('Changed patch source: ' + path)
    for name, digest in diagnostic['adapter_sources'].items():
        if sha((ROOT / 'src/fex' / name).read_bytes()) != digest:
            raise ValueError('Changed adapter: ' + name)
    if blob == control_nro or b'[FEX3-EVENT]' not in blob:
        raise ValueError('Missing event observer in diagnostic binary')
    record = {
        'kind': 'read-only event diagnostic', 'target': 'Nintendo Switch / Horizon ARM64',
        'hardware_tested': False, 'runtime_fixes': False, 'replaces': [NRO],
        'control_nro_sha256': control['nro_sha256'],
        'nro_sha256': diagnostic['nro_sha256'],
        'native_elf_sha256': diagnostic['native_elf_sha256'],
        'native_source_delta': delta, 'metadata': metadata,
    }
    readme = (
        'PES13-NX FEX3 event diagnostic — NRO-only, belum diuji di Switch.\n\n'
        '1. Tutup game lewat HOME lalu X. Backup NRO aktif sebelum mengganti.\n'
        '2. Ekstrak ZIP ini ke root SD; hanya switch/pes13-fex/pes13-fex.nro diganti.\n'
        '3. Pertahankan DLL, settings.dat, dxvk.conf, cache, save, clock, preset.\n'
        '4. Rekam video dari sebelum kickoff pertama: jam, HUD, pemain terlihat.\n'
        '5. Rekam replay pemicu slow-mo dan replay pemulih, catat detik sejak buka app.\n'
        '6. Tutup game; simpan switch/pes13-fex/fex-runtime.log sebelum buka lagi.\n'
        'Log [FEX3-EVENT] memberi interval 1 detik dari flusher; raw state/scale\n'
        'bukan bukti scene atau laju simulasi. Snapshot event aktif di NRO\n'
        'diagnostik meski fex_game_timing=0; video tetap diperlukan.\n'
        'Rollback: pulihkan NRO asli yang sudah di-backup.\n'
    ).encode()
    files = {NRO: blob, 'README.txt': readme,
             'manifest.json': (json.dumps(record, indent=2) + '\n').encode()}
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'x', zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            archive.writestr(name, content)
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(files) \
                or any(archive.read(name) != content for name, content in files.items()):
            raise RuntimeError('Archive verification failed')
    record['archive_sha256'] = sha(destination.read_bytes())
    record['archive_path'] = str(destination.resolve())
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control', type=Path, default=ROOT / 'local/fex3/control')
    parser.add_argument('--diagnostic', type=Path, default=ROOT / 'local/fex3/event-diagnostic')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/pes13-fex3-event-diagnostic.zip')
    args = parser.parse_args()
    print(json.dumps(package(args.control, args.diagnostic, args.output), indent=2))


if __name__ == '__main__':
    main()
