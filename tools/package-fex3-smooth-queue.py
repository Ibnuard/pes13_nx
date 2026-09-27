"""Package a single-option DXVK pacing candidate and exact baseline rollback."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TARGET = 'switch/pes13-fex/drive_c/PES13/dxvk.conf'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def options(data):
    result = {}
    for line in data.decode().splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        key, value = map(str.strip, line.split('=', 1))
        if key in result:
            raise ValueError('Duplicate option: ' + key)
        result[key] = value
    return result


def main():
    baseline = (ROOT / 'config/fex/dxvk.conf').read_bytes()
    candidate = (ROOT / 'config/fex/dxvk-smooth-queue.conf').read_bytes()
    before, after = options(baseline), options(candidate)
    delta = {key: [before.get(key), after.get(key)] for key in before.keys() | after.keys()
             if before.get(key) != after.get(key)}
    if delta != {'d3d9.maxFrameLatency': ['1', '2']}:
        raise ValueError('Unexpected config change: ' + repr(delta))
    analysis = (ROOT / 'local/fex3/smooth-queue/log-analysis.json').read_bytes()
    report = json.loads(analysis)
    snapshot = ROOT / 'local/fex3/smooth-queue/before' / report['sha256'] / 'fex-runtime.log'
    if sha(snapshot.read_bytes()) != report['sha256']:
        raise ValueError('Baseline evidence mismatch')
    files = {TARGET: candidate, 'rollback/' + TARGET: baseline,
             'README.md': (ROOT / 'docs/FEX3-SMOOTH-QUEUE.md').read_bytes(),
             'evidence/log-analysis.json': analysis}
    manifest = {
        'kind': 'DXVK two-frame queue pacing candidate', 'hardware_tested': False,
        'stutter_fix_verified': False, 'requires_existing_build': 'pes13-fex3-hang-audit',
        'replaces': [TARGET], 'options_delta': delta,
        'baseline_log_sha256': report['sha256'],
        'files': {name: sha(blob) for name, blob in sorted(files.items())},
    }
    files['manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    archive = ROOT / 'dist/pes13-fex3-smooth-queue.zip'
    folder = archive.with_suffix('')
    if folder.exists() or archive.exists():
        raise FileExistsError('Preserve existing package; choose a new candidate name')
    if {name for name in files if name.startswith('switch/')} != {TARGET}:
        raise ValueError('Unexpected active overlay file')
    folder.mkdir(parents=True)
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
        for name, blob in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 28, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, blob)
            target = folder / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None or set(z.namelist()) != set(files):
            raise RuntimeError('ZIP validation failed')
        for name, blob in files.items():
            if z.read(name) != blob or (folder / name).read_bytes() != blob:
                raise RuntimeError('Readback mismatch: ' + name)
    result = {'path': str(archive), 'bytes': archive.stat().st_size,
              'sha256': sha(archive.read_bytes()), 'active_files': [TARGET],
              'options_delta': delta, 'readback_verified': True}
    (ROOT / 'local/fex3/smooth-queue/package.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
