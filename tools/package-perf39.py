"""Package one PERF39 NRO and an optional configuration-only diagnostic overlay."""
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
import hashlib
import io
import json

project = Path(__file__).resolve().parents[1]
work = project / 'local/perf39'
prefix = 'switch/pes13-nx/'
sha = lambda data: hashlib.sha256(data).hexdigest()


def archive(path, files):
    buffer = io.BytesIO()
    with ZipFile(buffer, 'w', ZIP_DEFLATED) as target:
        for name, data in sorted(files.items()):
            assert not name.startswith('/') and '..' not in Path(name).parts
            info = ZipInfo(name, (2026, 9, 23, 0, 0, 0))
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
    assert report['source_restored'] and report['capture_host_test'] == 'PASS'
    assert report['native_pass_source_identical_to_perf38']
    nro = (work / 'payload' / prefix / 'pes13-nx.nro').read_bytes()
    assert sha(nro) == json.loads((work / 'build.json').read_text())['nro_sha256']
    with ZipFile(project / 'dist/pes13-perf38-region-fusion.zip') as baseline_zip:
        assert baseline_zip.testzip() is None
        old_manifest = json.loads(baseline_zip.read('PERF38-manifest.json'))
        old = {name: baseline_zip.read(name) for name in baseline_zip.namelist()
               if name != 'PERF38-manifest.json'}
    assert all(sha(data) == old_manifest['files'][name] for name, data in old.items())
    files = dict(old)
    files[prefix + 'pes13-nx.nro'] = nro
    files['PERF39.md'] = (project / 'docs/PERF39.md').read_bytes()
    config = files[prefix + 'configuration.ini']
    assert b'profile=0' in config and b'perf17_capture=0' in config
    assert b'perf38_region_fusion=1' in config
    assert sum(name.endswith('.nro') for name in files) == 1
    assert not any('/users/' in name or name.lower().endswith(
        ('.exe', '.reg', '.dat', '.log')) for name in files)
    manifest = {
        'variant': 'PERF39 capture repair', 'base': 'PERF38 region fusion',
        'nro_metadata': report['nro_metadata'], 'nro_sha256': sha(nro),
        'changed_runtime_files': [prefix + 'pes13-nx.nro'],
        'gameplay_policy_changed': False, 'hardware_tested': False,
        'target_verified': False, 'target_match_fps': 30,
        'files': {name: sha(data) for name, data in sorted(files.items())},
    }
    files['PERF39-manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    main_package = archive(project / 'dist/pes13-perf39-capture-repair.zip', files)
    with ZipFile(project / 'dist/pes13-perf38-diagnostics-overlay.zip') as diagnostic_zip:
        assert diagnostic_zip.testzip() is None
        diagnostic = {name: diagnostic_zip.read(name) for name in diagnostic_zip.namelist()
                      if name not in ('PERF38-diagnostics-manifest.json', 'PERF38.md')}
    assert b'profile=1' in diagnostic[prefix + 'configuration.ini']
    assert b'perf17_capture=1' in diagnostic[prefix + 'configuration.ini']
    diagnostic['PERF39.md'] = files['PERF39.md']
    diagnostic['PERF39-diagnostics-manifest.json'] = (json.dumps({
        'requires_nro_sha256': sha(nro), 'contains_nro': False,
        'files': {name: sha(data) for name, data in sorted(diagnostic.items())},
    }, indent=2) + '\n').encode()
    overlay = archive(project / 'dist/pes13-perf39-diagnostics-overlay.zip', diagnostic)
    result = {'main': main_package, 'optional_diagnostics': overlay}
    (work / 'packages.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
