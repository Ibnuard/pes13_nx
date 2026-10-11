"""Seal the user-tested v0.4.1 keyboard NRO and automatic forwarder for CI.

The r6 build baseline remains immutable. This promotion replaces only its NRO
and forwarder, preserving every runtime DLL and retaining source/test evidence.
"""
import argparse
import importlib.util
import json
from pathlib import Path
from release_package import ROOT, NRO, NSP, encoded, fingerprints, read_runtime, sha, write_zip

BASE_SHA = '4e065e65f1d6699b0233a558b0730ddc77f55f7a0f96405ce57c665f8402a88e'
NRO_SHA = '8f8d1d32a97bd1c3d7788a1333628c6052b73747985877f8f090fc201b835b07'
NSP_SHA = 'b100b2aa1a28e49316e67e16e74687fe6be74e6553e196d41252730bed2ecbe2'
AUTO_NSP = 'PES13-FEXTendo.nsp'


def promote(base, candidate, forwarder, output, lock_output):
    baseline = json.loads((ROOT / 'release/runtime-lock.json').read_text())
    if baseline['sha256'] != BASE_SHA:
        raise ValueError('Expected the immutable original r6 baseline')
    files = read_runtime(base, baseline)
    inventory = json.loads((candidate / 'manifest.json').read_text())
    preview = {n: (candidate / n).read_bytes() for n in inventory['files']}
    if {n: sha(d) for n, d in preview.items()} != inventory['files']:
        raise ValueError('Delivered keyboard-frame inventory differs')
    report = json.loads(preview['evidence/build.json'])
    if (not report['built'] or report['version'] != '0.4.1'
            or report['build_revision'] != 'keyboard-frame'
            or report['nro_sha256'] != NRO_SHA or sha(preview[NRO]) != NRO_SHA):
        raise ValueError('Expected the exact user-tested NRO')
    for n, digest in report['input_sources'].items():
        if sha((ROOT / n).read_bytes()) != digest:
            raise ValueError('Tested build input changed: ' + n)
    for name in inventory['checks']:
        receipt = json.loads(preview['evidence/' + name + '.json'])
        if not receipt['passed']:
            raise ValueError('Failed test receipt: ' + name)
        for key in ('elf_sha256', 'native_elf_sha256'):
            if key in receipt and receipt[key] != report['elf_sha256']:
                raise ValueError('Test receipt belongs to another build: ' + name)
        for group in ('sources', 'test_sources'):
            for n, digest in receipt.get(group, {}).items():
                if sha((ROOT / n).read_bytes()) != digest:
                    raise ValueError('Test source changed: ' + n)
    confirmation = json.loads((ROOT / 'release/v0.4.1-device-confirmation.json').read_text())
    if confirmation['nro_sha256'] != NRO_SHA or confirmation['keyboard_confirmed_working'] is not True:
        raise ValueError('Missing scoped device confirmation')
    f_report = json.loads((forwarder / 'forwarder-build.json').read_text())
    nsp = (forwarder / 'forwarders' / AUTO_NSP).read_bytes()
    if sha(nsp) != NSP_SHA:
        raise ValueError('Automatic forwarder differs from tested artifact')
    spec = importlib.util.spec_from_file_location('auto_metadata', ROOT / 'tests/pes13_forwarder_metadata.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    metadata = module.inspect_forwarder(nsp, f_report)
    files[NRO] = preview[NRO]
    del files[NSP]
    files[AUTO_NSP] = nsp
    for name, data in preview.items():
        if name != NRO:
            files['source/production-v0.4.1/' + name] = data
    files['evidence/forwarder-auto/build.json'] = encoded(f_report)
    files['evidence/forwarder-auto/metadata.json'] = encoded(metadata)
    files['evidence/production-v0.4.1/device-confirmation.json'] = encoded(confirmation)
    # Include the current release transport and tests as corresponding source.
    for folder in ('tools', 'tests', 'docs'):
        for p in sorted((ROOT / folder).rglob('*')):
            if p.is_file() and p.suffix in ('.py', '.c', '.cpp', '.h', '.sh', '.md') and '__pycache__' not in p.parts:
                files['source/production-v0.4.1/repository/' + p.relative_to(ROOT).as_posix()] = p.read_bytes()
    binaries = dict(baseline['binaries'])
    del binaries[NSP]
    binaries.update({NRO: NRO_SHA, AUTO_NSP: NSP_SHA})
    for n, digest in binaries.items():
        if sha(files[n]) != digest:
            raise ValueError('Baseline runtime dependency changed: ' + n)
    promotion = {'baseline_runtime_sha256': BASE_SHA, 'nro_sha256': NRO_SHA,
                 'native_elf_sha256': report['elf_sha256'], 'forwarder_sha256': NSP_SHA,
                 'binary_replacements': [NRO, NSP], 'checks': inventory['checks'],
                 'device_confirmation': confirmation, 'source_fingerprints': fingerprints()}
    files['evidence/production-v0.4.1/promotion.json'] = encoded(promotion)
    files['runtime-manifest.json'] = encoded({'kind': 'production-v0.4.1-runtime',
        'files': {n: sha(d) for n, d in sorted(files.items())}})
    output.parent.mkdir(parents=True, exist_ok=True)
    write_zip(output, files)
    lock = {'schema': 1, 'tag': 'runtime-production-v0.4.1', 'asset': output.name,
            'sha256': sha(output.read_bytes()), 'runtime_version': '0.4.1', 'release_tag': 'v0.4.1',
            'nro_title': 'PES13-FEXTendo', 'forwarder_filename': AUTO_NSP,
            'forwarder_kind': 'fxtauto-v1', 'binaries': binaries,
            'source_fingerprints': promotion['source_fingerprints'], 'device_confirmation': confirmation}
    read_runtime(output, lock)
    lock_output.write_bytes(encoded(lock))
    print(json.dumps({'archive': str(output), 'sha256': lock['sha256'], 'nro_sha256': NRO_SHA}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'candidate', 'forwarder', 'output', 'lock-output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    promote(args.base, args.candidate, args.forwarder, args.output, args.lock_output)
