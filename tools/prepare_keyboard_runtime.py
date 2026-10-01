"""Promote the tested keyboard-v4 NRO over the immutable production dependencies.

Both input archives are pinned to the previously delivered artifacts. This
does not rebuild or change the FEX DLL, forwarder, or Windows dependency set.
"""
import argparse
import json
from pathlib import Path
import zipfile

from release_package import ROOT, NRO, sha, encoded, fingerprints, read_runtime, safe_name, write_zip

BASE_SHA = '22affc1331126020d1adc79ad6013cca34077c807bd7004fed2a3e7fa2e2b4a5'
KEYBOARD_SHA = '85103b4c21f6c7667934b98f098dc8f877e2f438b3c1150c697b6097db3a9f0d'
NRO_SHA = '0a4823ade25a5a2914fe524798c4af59accd76a74bb1ba837e4f0b1414993ea5'
TESTS = ('keyboard', 'host-keyboard', 'focus', 'overlay', 'controllers',
         'hid-startup', 'silent', 'startup', 'maintenance', 'render')


def promote(base, base_lock, keyboard, output, lock_path):
    lock = json.loads(base_lock.read_text())
    if lock['sha256'] != BASE_SHA or sha(keyboard.read_bytes()) != KEYBOARD_SHA:
        raise ValueError('Expected the approved production-v1 and keyboard-v4 inputs')
    files = read_runtime(base, lock)
    for name, digest in lock['binaries'].items():
        if sha(files[name]) != digest:
            raise ValueError('Baseline binary differs: ' + name)
    with zipfile.ZipFile(keyboard) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate keyboard archive member')
        preview = {}
        for name in names:
            safe_name(name)
            preview[name] = archive.read(name)
    inventory = json.loads(preview.pop('manifest.json'))
    if {n: sha(d) for n, d in preview.items()} != inventory['files']:
        raise ValueError('Keyboard archive inventory mismatch')
    if {n for n in preview if n.startswith('switch/')} != {NRO}:
        raise ValueError('Keyboard preview must replace only the NRO')
    report = json.loads(preview['evidence/build-report.json'])
    if (not report['passed'] or not report['live_keyboard_overlay']
            or not report['native_keyboard_preview'] or report.get('runtime_image')
            or report['baseline_nro_sha256'] != sha(files[NRO])
            or sha(preview[NRO]) != report['nro_sha256'] or report['nro_sha256'] != NRO_SHA):
        raise ValueError('Keyboard binary/build provenance differs from the tested version')
    for name, digest in report['feature_sources'].items():
        if sha((ROOT / name).read_bytes()) != digest or sha(preview['source/' + name]) != digest:
            raise ValueError('Keyboard build source changed: ' + name)
    for name in TESTS:
        test = json.loads(preview['evidence/' + name + '-test.json'])
        if not test['passed'] or test['native_elf_sha256'] != report['native_elf_sha256']:
            raise ValueError('Keyboard test belongs to a different build: ' + name)
        for path, digest in test.get('test_sources', {}).items():
            if sha((ROOT / path).read_bytes()) != digest:
                raise ValueError('Keyboard test source changed: ' + path)
        for path, digest in test.get('screenshots', {}).items():
            if sha(preview['evidence/' + path]) != digest:
                raise ValueError('Keyboard render evidence changed: ' + path)
    for name, data in preview.items():
        if name == NRO:
            files[name] = data
        elif name.startswith(('source/', 'evidence/')):
            first, rest = name.split('/', 1)
            files[first + '/keyboard-v4/' + rest] = data
        elif name == 'README.txt':
            files['source/keyboard-v4/README.txt'] = data
        else:
            raise ValueError('Unexpected keyboard member: ' + name)
    binaries = dict(lock['binaries'])
    binaries[NRO] = sha(files[NRO])
    for name, digest in binaries.items():
        if name != NRO and sha(files[name]) != digest:
            raise ValueError('Production dependency changed: ' + name)
    promotion = {'base_runtime_sha256': BASE_SHA, 'keyboard_preview_sha256': KEYBOARD_SHA,
                 'native_elf_sha256': report['native_elf_sha256'], 'nro_sha256': NRO_SHA,
                 'checks': list(TESTS), 'binary_replacements': [NRO],
                 'feature_sources': report['feature_sources'],
                 'source_fingerprints': fingerprints()}
    files['evidence/keyboard-v4/promotion.json'] = encoded(promotion)
    files['runtime-manifest.json'] = encoded({
        'kind': 'production-v1-launchfix-keyboard-v4-runtime',
        'files': {n: sha(d) for n, d in sorted(files.items())}})
    output.parent.mkdir(parents=True, exist_ok=True)
    write_zip(output, files)
    new_lock = {'schema': 1, 'tag': 'runtime-keyboard-v4', 'asset': output.name,
                'sha256': sha(output.read_bytes()), 'runtime_version': lock['runtime_version'],
                'binaries': binaries, 'source_fingerprints': promotion['source_fingerprints']}
    read_runtime(output, new_lock)
    lock_path.write_bytes(encoded(new_lock))
    print(json.dumps({'runtime': str(output), 'sha256': new_lock['sha256'],
                      'nro_sha256': NRO_SHA, 'binary_replacements': [NRO]}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--base-lock', type=Path, required=True)
    parser.add_argument('--keyboard', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--lock-output', type=Path, default=ROOT / 'release/runtime-lock.json')
    args = parser.parse_args()
    promote(args.base, args.base_lock, args.keyboard, args.output, args.lock_output)
