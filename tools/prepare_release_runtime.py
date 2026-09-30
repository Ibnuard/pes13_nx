"""Prepare the first immutable release input from reviewed local artifacts.

Only explicitly listed runtime files are read from --extra-dlls; never copy a
live SD card, registry, game directory or keyset wholesale.
"""
import argparse
import json
from pathlib import Path
import zipfile

from release_package import ROOT, PREFIX, NRO, NSP, FEX, sha, encoded, fingerprints, write_zip


def checked(path, digest):
    data = path.read_bytes()
    if sha(data) != digest:
        raise ValueError('Wrong input hash: ' + str(path))
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wine-release', type=Path, required=True)
    parser.add_argument('--extra-dlls', type=Path, required=True, help='Working drive_c/windows/syswow64 folder')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    deps = json.loads((ROOT / 'dependencies.json').read_text())
    checked(args.wine_release, deps['wine_nx']['release_archive_sha256'])
    files = {}
    replacements = {'drive_c/windows/system32/winebox64.dll',
                    'drive_c/windows/system32/ntdll.dll', 'drive_c/windows/system32/wow64.dll',
                    'drive_c/dxvk/d3d9.dll'}
    with zipfile.ZipFile(args.wine_release) as z:
        for row in json.loads((ROOT / 'config/runtime-files.json').read_text()):
            name = row['path']
            if name in replacements:
                continue
            original = 'switch/wine/' + name
            if original in z.namelist():
                data = z.read(original)
            elif name.startswith('drive_c/windows/syswow64/'):
                data = checked(args.extra_dlls / Path(name).name, row['sha256'])
            else:
                raise ValueError('Missing runtime dependency: ' + name)
            if sha(data) != row['sha256']:
                raise ValueError('Changed baseline dependency: ' + name)
            files[PREFIX + name] = data
    base = ROOT / 'dist/pes13-fextendo-v3.6-fast-api-v1.zip'
    checked(base, 'fe3011bd1bbddddc998e6128cf5ca0aa6be5cdcd1cb126807ed786a8539bbf16')
    with zipfile.ZipFile(base) as z:
        for n in z.namelist():
            if n.startswith((PREFIX + 'launcher/', PREFIX + 'fex_')):
                files[n] = z.read(n)
    production = ROOT / 'dist/pes13-fextendo-production-v1-launchfix-dfe-rollback.zip'
    checked(production, 'c5a310d40a2d81b7fd152e0504c34a6bbc050749bf6b0a815e04706aae6d84ef')
    with zipfile.ZipFile(production) as z:
        recipe = json.loads(z.read('evidence/runtime/runtime-build.json'))
        for n in z.namelist():
            if n in (NRO, FEX) or n.startswith(('source/', 'evidence/', 'licenses/')):
                files[n] = z.read(n)
    native = ROOT / 'local/fex3/production-v1-launchfix/runtime/payload'
    for n, key in [('ntdll.dll', 'ntdll_sha256'), ('wow64.dll', 'wow64_sha256')]:
        files[PREFIX + 'drive_c/windows/system32/' + n] = checked(native / n, recipe[key])
    for target in ('drive_c/PES13/d3d9.dll', 'drive_c/dxvk/d3d9.dll'):
        files[PREFIX + target] = files[PREFIX + 'launcher/renderers/dxvk-3.1.1/d3d9.dll']
    for target in ('drive_c/PES13/dxvk.conf', 'launcher/presets/dxvk.conf'):
        files[PREFIX + target] = files[PREFIX + 'launcher/renderers/dxvk-3.1.1/dxvk.conf']
    files[PREFIX + 'launcher/renderer.txt'] = b'0\n'
    files[PREFIX + 'launcher/renderer-choice.txt'] = b'0\n'
    files[PREFIX + 'launcher/selected.txt'] = b'0\n'
    forwarder = ROOT / 'dist/fextendo-forwarder'
    report = json.loads((forwarder / 'build.json').read_text())
    files[NSP] = checked(forwarder / NSP, report['nsp_sha256'])
    for name in ('build.json', 'verification.json'):
        files['evidence/forwarder/' + name] = (forwarder / name).read_bytes()
    for folder in ('licenses', 'source'):
        for p in (forwarder / folder).rglob('*'):
            if p.is_file():
                files[folder + '/forwarder/' + p.relative_to(forwarder / folder).as_posix()] = p.read_bytes()
    binaries = {n: sha(d) for n, d in files.items()
                if n.startswith(PREFIX) and n.endswith(('.nro', '.dll', '.drv', '.acm')) or n == NSP}
    manifest = {'kind': 'production-v1-launchfix-dfe-rollback-runtime',
                'files': {n: sha(d) for n, d in sorted(files.items())}}
    files['runtime-manifest.json'] = encoded(manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_zip(args.output, files)
    lock = {'schema': 1, 'tag': 'runtime-production-v1', 'asset': args.output.name,
            'sha256': sha(args.output.read_bytes()), 'runtime_version': '0.3.7',
            'binaries': binaries, 'source_fingerprints': fingerprints()}
    (ROOT / 'release/runtime-lock.json').write_bytes(encoded(lock))
    print(json.dumps({'runtime': str(args.output), 'sha256': lock['sha256'], 'files': len(files)}, indent=2))


if __name__ == '__main__':
    main()
