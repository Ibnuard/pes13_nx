"""Promote the exact delivered r6 NRO; retain the pinned keyboard-v4 dependencies."""
import argparse
import json
from pathlib import Path
from release_package import ROOT, NRO, sha, encoded, fingerprints, read_runtime, write_zip

BASE_SHA = '119ab5400d23c65af661994ba38868f379aaf4ea83f679b110468c53bfac38bb'
NRO_SHA = '9d5acf823e5494f5d04e8b5ebd7cd54487e5033de4df09be3e8e76db1cf9eb06'


def promote(base, base_lock, candidate, output, lock_output):
    lock = json.loads(base_lock.read_text())
    if lock['sha256'] != BASE_SHA:
        raise ValueError('Expected the immutable keyboard-v4 runtime')
    files = read_runtime(base, lock)
    inventory = json.loads((candidate / 'manifest.json').read_text())
    preview = {n: (candidate / n).read_bytes() for n in inventory['files']}
    if {n: sha(d) for n, d in preview.items()} != inventory['files']:
        raise ValueError('Delivered r6 package inventory differs')
    report = json.loads(preview['evidence/build-report.json'])
    if not report['passed'] or report['nro_sha256'] != NRO_SHA or sha(preview[NRO]) != NRO_SHA:
        raise ValueError('Expected the delivered r6 binary')
    for group in ('feature_sources', 'build_scripts'):
        for n, digest in report[group].items():
            if sha((ROOT / n).read_bytes()) != digest or sha(preview['source/' + n]) != digest:
                raise ValueError('r6 build source changed: ' + n)
    for name in inventory['receipts']:
        receipt = json.loads(preview['evidence/' + name + '.json'])
        if not receipt['passed']:
            raise ValueError('Failed receipt: ' + name)
        for key in ('native_elf_sha256', 'nro_sha256'):
            if key in receipt and receipt[key] != report[key]:
                raise ValueError('Receipt belongs to another build: ' + name)
        for group in ('sources', 'test_sources'):
            for n, digest in receipt.get(group, {}).items():
                if sha((ROOT / n).read_bytes()) != digest:
                    raise ValueError('Test source changed: ' + n)
    if {n for n in preview if n.startswith('switch/')} != {NRO}:
        raise ValueError('r6 must replace only the NRO')
    for name, data in preview.items():
        if name == NRO:
            files[name] = data
        else:
            files['source/production-r6/' + name] = data
    binaries = dict(lock['binaries'])
    binaries[NRO] = NRO_SHA
    for n, digest in binaries.items():
        if sha(files[n]) != digest:
            raise ValueError('Production dependency changed: ' + n)
    promotion = {'base_runtime_sha256': BASE_SHA, 'nro_sha256': NRO_SHA,
                 'native_elf_sha256': report['native_elf_sha256'],
                 'checks': inventory['receipts'], 'binary_replacements': [NRO],
                 'source_fingerprints': fingerprints()}
    files['evidence/production-r6/promotion.json'] = encoded(promotion)
    files['runtime-manifest.json'] = encoded({'kind': 'production-r6-runtime',
        'files': {n: sha(d) for n, d in sorted(files.items())}})
    output.parent.mkdir(parents=True, exist_ok=True)
    write_zip(output, files)
    new_lock = {'schema': 1, 'tag': 'runtime-production-r6', 'asset': output.name,
                'sha256': sha(output.read_bytes()), 'runtime_version': '0.3.8-r6',
                'binaries': binaries, 'source_fingerprints': promotion['source_fingerprints']}
    read_runtime(output, new_lock)
    lock_output.write_bytes(encoded(new_lock))
    print(json.dumps({'archive': str(output), 'sha256': new_lock['sha256'], 'nro': NRO_SHA}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('base', 'base-lock', 'candidate', 'output', 'lock-output'):
        p.add_argument('--' + n, type=Path, required=True)
    a = p.parse_args()
    promote(a.base, a.base_lock, a.candidate, a.output, a.lock_output)
