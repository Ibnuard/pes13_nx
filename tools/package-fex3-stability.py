"""Package the matched FEX3 stability runtime/module with validated 540p settings."""
import argparse
import binascii
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import struct
import subprocess
import tempfile
import zipfile

from nro_assets import inspect_nro

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'switch/pes13-fex/'
SETTINGS = (
    'drive_c/KONAMI/Pro Evolution Soccer 2013/settings.dat',
    'drive_c/users/steamuser/Documents/KONAMI/Pro Evolution Soccer 2013/settings.dat',
    'drive_c/PES13/settings.dat',
)
PAYLOAD = {
    'pes13-fex.nro', 'configuration.ini', 'drive_c/PES13/dxvk.conf',
    'drive_c/windows/system32/libwow64fex.dll',
    'drive_c/windows/system32/ntdll.dll', 'drive_c/windows/system32/wow64.dll',
    'drive_c/fex-stress.exe', *SETTINGS,
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked(path, expected):
    data = Path(path).read_bytes()
    if sha(data) != expected:
        raise ValueError('Hash mismatch: ' + str(path))
    return data


def read_json(path):
    return json.loads(Path(path).read_text())


def checked_report(data, expected):
    report = json.loads(data)
    if report.get('passed') is not True or any(report.get(k) != v for k, v in expected.items()):
        raise ValueError('Invalid/stale validation receipt')
    return report


def resize_settings(data, width, height):
    spec = importlib.util.spec_from_file_location('pes_settings', ROOT / 'tools/make-settings.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.validate(data)
    if width * 9 != height * 16 or min(width, height) <= 0:
        raise ValueError('Expected positive 16:9 resolution')
    resized = bytearray(data)
    struct.pack_into('<II', resized, 0x10, width, height)
    struct.pack_into('<H', resized, 0x0c, 0)
    struct.pack_into('<H', resized, 0x0c, module.crc16(resized))
    module.validate(resized)
    independent = bytearray(resized)
    independent[12:14] = b'\0\0'
    if struct.unpack_from('<H', resized, 12)[0] != (~binascii.crc_hqx(independent, 0) & 0xffff):
        raise ValueError('Independent CRC check failed')
    allowed = set(range(12, 14)) | set(range(16, 24))
    if any(a != b and i not in allowed for i, (a, b) in enumerate(zip(data, resized))):
        raise ValueError('Unrelated settings changed')
    return bytes(resized)


def verify_executable(elf, blob):
    with tempfile.TemporaryDirectory(prefix='fex-nro-verify-') as directory:
        output = Path(directory) / 'bare.nro'
        subprocess.run(['/opt/devkitpro/tools/bin/elf2nro', str(elf), str(output)],
                       check=True, capture_output=True, timeout=60)
        if output.read_bytes() != blob[:struct.unpack_from('<I', blob, 0x18)[0]]:
            raise ValueError('NRO executable differs from tested ELF')


def collect(candidate):
    runtime, module = candidate / 'runtime', candidate / 'module'
    build, fex = read_json(runtime / 'runtime-build.json'), read_json(module / 'build.json')
    patches, fp = read_json(runtime / 'wine-patches.json'), read_json(module / 'patches.json')
    for flag in ('runtime_fixes', 'stability', 'diagnostic', 'resume_gate', 'samecore_yield'):
        if build.get(flag) is not True:
            raise ValueError('Missing stability build flag: ' + flag)
    if build.get('box64_engine_linked') is not False or fex.get('horizon_adapter') is not True:
        raise ValueError('Unexpected runtime/module type')
    if build['toolchain_path'] != fex['toolchain_path'] or fp['fex_commit'] != fex['fex_commit']:
        raise ValueError('Runtime/module recipe mismatch')
    for name, digest in fex['adapter_sources'].items():
        checked(ROOT / name, digest)
        if name.startswith('src/fex/') and build['adapter_sources'].get(Path(name).name) != digest:
            raise ValueError('Native/PE adapter source mismatch: ' + name)
    for name, digest in build['adapter_sources'].items():
        checked(ROOT / 'src/fex' / name, digest)
    for name, digest in build['patch_sources'].items():
        checked(ROOT / name, digest)

    dll = checked(module / 'libwow64fex.dll', fex['sha256'])
    nro = checked(runtime / 'payload/pes13-fex.nro', build['nro_sha256'])
    elf = runtime / 'reference/pes13-fex.elf'
    checked(elf, build['native_elf_sha256'])
    metadata = inspect_nro(nro, (ROOT / 'assets/icon.jpg').read_bytes(),
                           expected_title='PES13-NX FEX3', expected_version='0.3.0')
    verify_executable(elf, nro)
    for marker, data in ((b'pes13-fex3-stability-540p', nro),
                         (b'[FEX3-RESUME] isolated self-suspend wake', nro),
                         (b'[FEX3-FP] context v1', dll),
                         (b'[FEX3-ALIAS] generation-validated', dll)):
        if marker not in data:
            raise ValueError('Missing marker: ' + repr(marker))
    files = {PREFIX + 'pes13-fex.nro': nro,
             PREFIX + 'drive_c/windows/system32/libwow64fex.dll': dll}
    for name, field in (('ntdll.dll', 'ntdll_sha256'), ('wow64.dll', 'wow64_sha256'),
                        ('fex-stress.exe', 'guest_sha256')):
        target = 'drive_c/' + ('' if name.endswith('.exe') else 'windows/system32/') + name
        files[PREFIX + target] = checked(runtime / 'payload' / name, build[field])

    native = {'native_elf_sha256': build['native_elf_sha256']}
    pe = {'dll_sha256': fex['sha256']}
    source = patches['native-source']['dlls/ntdll/unix/horizon.c']
    context = next(p['patched_sha256'] for p in fp['files']
                   if p['path'] == 'Source/Windows/WOW64/Module.cpp')
    reports = {name: native for name in ('resume-binary', 'sync-binary', 'pipeline-binary', 'dispatch-binary')}
    reports.update({name: pe for name in ('fpu-binary', 'abi-binary', 'alias-binary')})
    reports.update({
        'samecore-binary': {**native, 'expected_yield_ns': 0},
        'profile-heap-binary': {**native, **pe},
        'unwind-binary': {**native, 'fex_sha256': fex['sha256'],
                          'ntdll_sha256': build['ntdll_sha256'], 'wow64_sha256': build['wow64_sha256']},
        'alias-generation': {'source_sha256': fex['adapter_sources']['src/fex/module_host.cpp'],
                             'mutation_without_generation_check_rejected': True},
        'fpu-context': {'source_sha256': context},
        'resume-host': {'source_sha256': source},
        'fpu-numerical': {},
    })
    for name, fields in reports.items():
        data = (candidate / (name + '.json')).read_bytes()
        report = checked_report(data, fields)
        if name == 'fpu-numerical':
            for path, digest in report['sources'].items():
                checked(ROOT / path, digest)
        files['evidence/' + name + '.json'] = data
    timer = (candidate / 'timer-affinity.txt').read_text().splitlines()[-1].encode()
    checked_report(timer, {'source_sha256': source, 'mode': 'as-is', 'suite': 'all'})
    files['evidence/timer-affinity.json'] = timer + b'\n'
    for directory, name in ((runtime, 'runtime-build.json'), (runtime, 'wine-patches.json'),
                            (module, 'build.json'), (module, 'patches.json')):
        files['evidence/' + directory.name + '-' + name] = (directory / name).read_bytes()

    settings = (ROOT / 'config/drive_c/users/steamuser/Documents/KONAMI/Pro Evolution Soccer 2013/settings.dat').read_bytes()
    for name in SETTINGS:
        files[PREFIX + name] = resize_settings(settings, 960, 540)
    files['profiles/720p/settings.dat'] = resize_settings(settings, 1280, 720)
    ini = (ROOT / 'config/fex/stability-540p.ini').read_bytes()
    files[PREFIX + 'configuration.ini'] = ini
    files['profiles/conservative-ordering.ini'] = ini.replace(b'fex_fastest=1', b'fex_fastest=0')
    files[PREFIX + 'drive_c/PES13/dxvk.conf'] = (ROOT / 'config/fex/dxvk.conf').read_bytes()
    files['README.md'] = (ROOT / 'docs/FEX3-STABILITY-540P.md').read_bytes()
    files['FEX-REUSABILITY-AUDIT-2026-09-27.md'] = (ROOT / 'docs/FEX-REUSABILITY-AUDIT-2026-09-27.md').read_bytes()
    files['THIRD_PARTY.md'] = (ROOT / 'THIRD_PARTY.md').read_bytes()
    files['licenses/Wine-and-PES13-LGPL-2.1.txt'] = (ROOT / 'LICENSE').read_bytes()
    files['licenses/PES13-FEX-adapter-MIT.txt'] = (ROOT / 'src/fex/LICENSE').read_bytes()
    for base, target in ((ROOT / 'licenses', 'licenses'), (module / 'licenses', 'licenses/FEX')):
        for path in sorted(base.rglob('*')):
            if path.is_file() and path.name != 'Box64-LICENSE.txt':
                files[target + '/' + path.relative_to(base).as_posix()] = path.read_bytes()
    record = {'kind': 'FEX3 stability + 540p candidate', 'hardware_tested': False,
              'fps_gain_verified': False, 'resolution': [960, 540], 'aspect': '16:9',
              'profile': 'Fastest', 'clock_changes': False,
              'requires': 'Existing playable FEX3 prefix, original game and unchanged Wine/DXVK dependencies',
              'fex_commit': fex['fex_commit'], 'metadata': metadata,
              'native_elf_sha256': build['native_elf_sha256'],
              'replaces': sorted(PREFIX + name for name in PAYLOAD),
              'files': {name: sha(data) for name, data in sorted(files.items())}}
    files['manifest.json'] = (json.dumps(record, indent=2) + '\n').encode()
    return files


def validate_boundary(files):
    for name in files:
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name or str(path) != name:
            raise ValueError('Unsafe archive path: ' + name)
    if {name for name in files if name.startswith('switch/')} != {PREFIX + name for name in PAYLOAD}:
        raise ValueError('Unexpected/missing Switch payload')


def write_package(files, output):
    validate_boundary(files)
    archive = Path(str(output) + '.zip')
    if output.exists() or archive.exists():
        raise FileExistsError('Refusing to overwrite an existing package: ' + str(output))
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as zipped:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 27, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zipped.writestr(info, data)
    with zipfile.ZipFile(archive) as zipped:
        if zipped.testzip() or set(zipped.namelist()) != set(files) or any(
                zipped.read(name) != data for name, data in files.items()):
            raise RuntimeError('Archive readback mismatch')
    output.mkdir()
    for name, data in files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        checked(path, sha(data))
    return {'archive': str(archive.resolve()), 'directory': str(output.resolve()),
            'sha256': sha(archive.read_bytes()), 'bytes': archive.stat().st_size,
            'files': len(files), 'hardware_tested': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, default=ROOT / 'local/fex3/stability-540p')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist/pes13-fex3-stability-540p')
    args = parser.parse_args()
    print(json.dumps(write_package(collect(args.candidate), args.output_dir), indent=2))


if __name__ == '__main__':
    main()
