"""Assemble a complete SD package from an explicitly approved binary runtime.

This is distribution CI, not a cross compiler. Source fingerprints prevent a
changed launcher from silently being released with the previous NRO/DLLs.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import tempfile
import zipfile

from nro_assets import inspect_nro

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'switch/pes13-fex/'
NRO = PREFIX + 'pes13-fex.nro'
NSP = 'FEXTendo-PES13.nsp'
FEX = PREFIX + 'drive_c/windows/system32/libwow64fex.dll'
SETTINGS = ('drive_c/KONAMI/Pro Evolution Soccer 2013/settings.dat',
            'drive_c/PES13/settings.dat',
            'drive_c/users/steamuser/Documents/KONAMI/Pro Evolution Soccer 2013/settings.dat')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def safe_name(name):
    p = PurePosixPath(name)
    if (not name or p.is_absolute() or '..' in p.parts or '\\' in name
            or ':' in name or p.as_posix() != name.rstrip('/')):
        raise ValueError('Unsafe archive path: ' + name)
    return p


def fingerprints(root=ROOT):
    paths = list((root / 'src').rglob('*'))
    paths += [p for p in (root / 'tools').glob('*.py')
              if 'patch' in p.name or p.name.startswith(('build-', 'fex2_prepare'))]
    paths += [root / 'dependencies.json', root / 'assets/fextendo-v3/nro-icon.jpg']
    return {p.relative_to(root).as_posix(): sha(p.read_bytes()) for p in sorted(paths)
            if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.md', '.pyc')}


def verify_sources(lock, root=ROOT):
    actual = fingerprints(root)
    changed = sorted(p for p in actual.keys() | lock['source_fingerprints'].keys()
                     if actual.get(p) != lock['source_fingerprints'].get(p))
    if changed:
        raise ValueError('Runtime source changed; rebuild and approve a new runtime input first: '
                         + ', '.join(changed))


def read_runtime(path, lock):
    if sha(path.read_bytes()) != lock['sha256']:
        raise ValueError('Runtime archive SHA256 mismatch')
    files = {}
    with zipfile.ZipFile(path) as z:
        for i in z.infolist():
            safe_name(i.filename)
            if (i.is_dir() or i.filename in files or stat.S_ISLNK(i.external_attr >> 16)
                    or i.file_size > 128 * 1024 * 1024):
                raise ValueError('Unexpected runtime member: ' + i.filename)
            files[i.filename] = z.read(i)
    manifest = json.loads(files.pop('runtime-manifest.json'))
    if {n: sha(d) for n, d in files.items()} != manifest['files']:
        raise ValueError('Runtime inventory/hash mismatch')
    return files


def write_zip(path, files, directories=()):
    """Explicit directory entries survive ZIP extraction and artifact upload."""
    with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in sorted(set(directories)):
            safe_name(name)
            info = zipfile.ZipInfo(name.rstrip('/') + '/', (2026, 1, 1, 0, 0, 0))
            info.external_attr = (stat.S_IFDIR | 0o755) << 16 | 0x10
            z.writestr(info, b'')
        for name, data in sorted(files.items()):
            safe_name(name)
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            z.writestr(info, data)


def verify_payload(files, lock):
    for name in files:
        safe_name(name)
        low = name.lower()
        if (low.endswith(('.reg', '.log', '.shm', '.exe', '.img', '.keys'))
                or any(x in low for x in ('lsfg', 'lossless', 'winebox64.dll', 'prod.keys', 'rld.dll'))
                or PurePosixPath(low).name in ('stdout.txt', 'stderr.txt', 'stdin.txt', '.ds_store')):
            # Sources and build receipts may describe old experiments; never ship their payloads.
            if not name.startswith(('source/', 'evidence/')):
                raise ValueError('Unexpected distributed file: ' + name)
    for n in (NRO, NSP, FEX, PREFIX + 'configuration.ini', PREFIX + 'launcher/font.bin',
              PREFIX + 'launcher/background.rgba', PREFIX + 'drive_c/PES13/d3d9.dll',
              PREFIX + 'share/wine/nls/locale.nls', *[PREFIX + n for n in SETTINGS]):
        if n not in files:
            raise ValueError('Missing required payload: ' + n)
    for n, digest in lock['binaries'].items():
        if sha(files[n]) != digest:
            raise ValueError('Changed approved binary: ' + n)
    metadata = inspect_nro(files[NRO], (ROOT / 'assets/fextendo-v3/nro-icon.jpg').read_bytes(),
                           expected_title='PES13 - FEXTendo', expected_version=lock['runtime_version'])
    forwarder = json.loads(files['evidence/forwarder/build.json'])
    if (forwarder['nsp_sha256'] != sha(files[NSP])
            or forwarder['icon_sha256'] != metadata['icon_sha256']
            or forwarder['address_space'] != '32-bit no-alias'
            or forwarder['cpu_cores'] != 4 or forwarder['svc_debug'] is not False
            or forwarder['nro_path'] != 'sdmc:/switch/pes13-fex/pes13-fex.nro'):
        raise ValueError('Forwarder identity/capabilities differ from approved NRO')
    spec = importlib.util.spec_from_file_location('forwarder', ROOT / 'tools/build-fextendo-forwarder.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if {n: sha(d) for n, d in module.pfs_files(files[NSP]).items()} != forwarder['nca_files']:
        raise ValueError('Forwarder NCA hashes differ from verified build')
    options = dict(line.strip().split('=', 1) for line in files[PREFIX + 'configuration.ini'].decode().splitlines()
                   if '=' in line and not line.lstrip().startswith('#'))
    if options.get('run_guest_tests') != '0' or options.get('production') != '1':
        raise ValueError('Release must launch the game in production mode')
    for n in SETTINGS:
        data = files[PREFIX + n]
        crc = 0
        for i, b in enumerate(data):
            crc ^= (0 if i in (12, 13) else b) << 8
            for _ in range(8):
                crc = ((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 0xffff
        if (len(data) != 852 or struct.unpack_from('<III', data) != (0x46434557, 2, 852)
                or struct.unpack_from('<H', data, 12)[0] != (~crc & 0xffff)):
            raise ValueError('Invalid PES settings preset: ' + n)
    # Check the actual packaged modules, not the developer's installed runtime.
    spec = importlib.util.spec_from_file_location('imports', ROOT / 'tools/audit-fex-imports.py')
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    with tempfile.TemporaryDirectory() as temp:
        dest = Path(temp)
        for name, data in files.items():
            if name.startswith(PREFIX + 'drive_c/windows/'):
                p = dest / name.removeprefix(PREFIX)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
        reports = {}
        for directory, machine, names in (
            ('system32', 0xaa64, ('ntdll.dll', 'wow64.dll', 'libwow64fex.dll')),
            ('syswow64', 0x14c, ('d3dx9_30.dll', 'xinput1_1.dll', 'xinput1_3.dll', 'windowscodecs.dll'))):
            folder = dest / 'drive_c/windows' / directory
            for n in names:
                print('Checking imports: ' + directory + '/' + n, flush=True)
                report = audit.audit(folder / n, folder, machine=machine)
                if not report['passed']:
                    raise ValueError('Incomplete runtime imports: ' + n + ': ' + str(report['issues'][:8]))
                reports[directory + '/' + n] = len(report['modules'])
    return {'nro': metadata, 'imports_checked': reports, 'hardware_tested': False}


def assemble(runtime, output, version, commit, lock_path=ROOT / 'release/runtime-lock.json'):
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}', version):
        raise ValueError('Invalid package version')
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Expected full source commit SHA')
    lock = json.loads(lock_path.read_text())
    verify_sources(lock)
    files = read_runtime(runtime, lock)
    directories = set()
    for p in sorted((ROOT / 'release/skeleton').rglob('*')):
        if p.is_symlink():
            raise ValueError('Symlink in release skeleton')
        name = p.relative_to(ROOT / 'release/skeleton').as_posix()
        if p.is_dir():
            directories.add(name + '/')
        elif p.name != '.gitkeep':
            # A skeleton is configuration only, never a back door for game binaries.
            if p.suffix.lower() not in ('.ini', '.txt', '.conf'):
                raise ValueError('Unexpected skeleton file: ' + name)
            files[name] = p.read_bytes()
    for n in SETTINGS:
        files[PREFIX + n] = (ROOT / 'config/fextendo/presets/medium-720.dat').read_bytes()
    for p in (ROOT / 'config/fextendo/presets').glob('*.dat'):
        files[PREFIX + 'launcher/presets/' + p.name] = p.read_bytes()
    files[PREFIX + 'drive_c/PES13/pes2013.wine-nx.txt'] = (ROOT / 'config/drive_c/PES13/pes2013.wine-nx.txt').read_bytes()
    checks = verify_payload(files, lock)
    files['README.txt'] = (ROOT / 'release/README.txt').read_bytes()
    files['THIRD_PARTY.md'] = (ROOT / 'THIRD_PARTY.md').read_bytes()
    for name in ('README.md', 'LICENSE', 'dependencies.json', 'docs/RELEASE-CI.md', 'tools/export-metadata.py'):
        files['source/release/' + name] = (ROOT / name).read_bytes()
    for n in files:
        directories.update(p.as_posix() + '/' for p in PurePosixPath(n).parents if p.as_posix() != '.')
    manifest = {'package_version': version, 'source_commit': commit, 'runtime_version': lock['runtime_version'],
                'runtime_sha256': lock['sha256'], 'runtime_tag': lock['tag'],
                'game_included': False, 'settings_included': True, 'checks': checks,
                'directories': sorted(directories), 'files': {n: sha(d) for n, d in sorted(files.items())}}
    files['manifest.json'] = encoded(manifest)
    output.mkdir(parents=True, exist_ok=False)
    archive = output / ('FEXTendo-' + version + '-sd.zip')
    write_zip(archive, files, directories)
    # Read back every member; CRCs, hashes and empty directories must survive.
    with zipfile.ZipFile(archive) as z:
        if z.testzip() or any(sha(z.read(n)) != d for n, d in manifest['files'].items()):
            raise ValueError('Package verification failed')
        if not directories <= set(z.namelist()):
            raise ValueError('Empty directories lost during packaging')
    (output / 'pes13-fex.nro').write_bytes(files[NRO])
    (output / NSP).write_bytes(files[NSP])
    (output / 'manifest.json').write_bytes(files['manifest.json'])
    (output / 'SHA256SUMS').write_text(''.join(sha(p.read_bytes()) + '  ' + p.name + '\n'
                                           for p in sorted(output.iterdir()) if p.is_file()))
    print(json.dumps({'passed': True, 'package': str(archive), 'files': len(files),
                      'directories': len(directories), 'checks': checks}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--version', required=True)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    assemble(args.runtime, args.output, args.version, args.commit)
