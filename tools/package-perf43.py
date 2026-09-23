"""Package a bounded JIT diagnostic build on top of PERF42."""
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
import hashlib
import io
import json

project = Path(__file__).resolve().parents[1]
work = project / 'local/perf43'
prefix = 'switch/pes13-nx/'
sha = lambda data: hashlib.sha256(data).hexdigest()


def archive(path, files):
    buffer = io.BytesIO()
    with ZipFile(buffer, 'w', ZIP_DEFLATED) as target:
        for name, data in sorted(files.items()):
            assert not name.startswith('/') and '..' not in Path(name).parts
            info = ZipInfo(name, (2026, 9, 24, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            target.writestr(info, data)
    raw = buffer.getvalue()
    if path.exists():
        assert path.read_bytes() == raw, 'Refusing to overwrite a changed package'
    else:
        with path.open('xb') as output:
            output.write(raw)
    with ZipFile(path) as check:
        assert check.testzip() is None
        assert all(check.read(name) == data for name, data in files.items())
    return {'path': str(path), 'sha256': sha(raw), 'bytes': len(raw)}


def main():
    report = json.loads((work / 'verification.json').read_text())
    assert report['source_restored'] and report['probe_asan_ubsan'] == 'PASS'
    assert report['native_pass_source_identical_to_perf42']
    nro = (work / 'payload' / prefix / 'pes13-nx.nro').read_bytes()
    assert sha(nro) == json.loads((work / 'build.json').read_text())['nro_sha256']
    with ZipFile(project / 'dist/pes13-perf42-startup-guard.zip') as baseline_zip:
        assert baseline_zip.testzip() is None
        old_manifest = json.loads(baseline_zip.read('PERF42-manifest.json'))
        old = {name: baseline_zip.read(name) for name in baseline_zip.namelist()
               if name != 'PERF42-manifest.json'}
    assert all(sha(data) == old_manifest['files'][name] for name, data in old.items())
    files = dict(old)
    files[prefix + 'pes13-nx.nro'] = nro
    for suffix in ('configuration.ini', 'drive_c/PES13/pes2013.wine-nx.txt'):
        name = prefix + suffix
        assert files[name].count(b'profile=0') == 1
        files[name] = files[name].replace(b'profile=0', b'profile=1')
    config = files[prefix + 'configuration.ini']
    assert b'perf42_startup_guard=1' in config and b'perf17_capture=0' in config
    files['PERF43.md'] = (project / 'docs/PERF43.md').read_bytes()
    changed = sorted(name for name in files if name.startswith(prefix) and
                     files[name] != old[name])
    assert changed == sorted([prefix + 'configuration.ini',
                              prefix + 'drive_c/PES13/pes2013.wine-nx.txt',
                              prefix + 'pes13-nx.nro'])
    assert sum(name.endswith('.nro') for name in files) == 1
    assert not any('/users/' in name or name.lower().endswith(
        ('.exe', '.reg', '.dat', '.log')) for name in files)
    manifest = {
        'variant': 'PERF43 match JIT probe', 'base': 'PERF42 startup guard',
        'nro_metadata': report['nro_metadata'], 'nro_sha256': sha(nro),
        'changed_runtime_files': changed, 'execution_policy_unchanged': True,
        'sampler_enabled': True, 'performance_improvement_claimed': False,
        'hardware_tested': False, 'files': {
            name: sha(data) for name, data in sorted(files.items())},
    }
    files['PERF43-manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    result = archive(project / 'dist/pes13-perf43-match-probe-r2.zip', files)
    (work / 'packages.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
