"""Package quiet PERF41 and a same-NRO control that retains PERF40."""
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
import hashlib
import io
import json

project = Path(__file__).resolve().parents[1]
work = project / 'local/perf41'
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
    assert report['source_restored'] and report['matrix_policy_host_test'] == 'PASS'
    assert report['native_pass_source_identical_to_perf40']
    nro = (work / 'payload' / prefix / 'pes13-nx.nro').read_bytes()
    assert sha(nro) == json.loads((work / 'build.json').read_text())['nro_sha256']
    with ZipFile(project / 'dist/pes13-perf40-early-round.zip') as baseline_zip:
        assert baseline_zip.testzip() is None
        old_manifest = json.loads(baseline_zip.read('PERF40-manifest.json'))
        old = {name: baseline_zip.read(name) for name in baseline_zip.namelist()
               if name != 'PERF40-manifest.json'}
    assert all(sha(data) == old_manifest['files'][name] for name, data in old.items())
    files = dict(old)
    files[prefix + 'pes13-nx.nro'] = nro
    config = files[prefix + 'configuration.ini']
    assert b'profile=0' in config and b'perf17_capture=0' in config
    assert b'perf40_early_round=1' in config and b'perf19_matrix=1' in config
    assert b'perf41_matrix_round' not in config
    config += b'\n# PERF41: exact measured matrix sibling. Set 0 for control.\nperf41_matrix_round=1\n'
    files[prefix + 'configuration.ini'] = config
    for doc in ('PERF40-RESULT.md', 'PERF41.md'):
        files[doc] = (project / 'docs' / doc).read_bytes()
    changed = sorted(name for name in files if name.startswith(prefix) and
                     files[name] != old[name])
    assert changed == [prefix + 'configuration.ini', prefix + 'pes13-nx.nro']
    assert sum(name.endswith('.nro') for name in files) == 1
    assert not any('/users/' in name or name.lower().endswith(
        ('.exe', '.reg', '.dat', '.log')) for name in files)
    manifest = {
        'variant': 'PERF41 matrix round', 'base': 'PERF40 early round',
        'nro_metadata': report['nro_metadata'], 'nro_sha256': sha(nro),
        'changed_runtime_files': changed, 'hardware_tested': False,
        'target_verified': False, 'target_match_fps': 30,
        'files': {name: sha(data) for name, data in sorted(files.items())},
    }
    files['PERF41-manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    main_package = archive(project / 'dist/pes13-perf41-matrix-round.zip', files)
    control_config = config.replace(b'perf41_matrix_round=1', b'perf41_matrix_round=0')
    assert control_config != config and control_config.count(b'perf41_matrix_round=0') == 1
    control = {prefix + 'configuration.ini': control_config,
               'PERF41.md': files['PERF41.md']}
    control['PERF41-control-manifest.json'] = (json.dumps({
        'requires_nro_sha256': sha(nro), 'contains_nro': False,
        'files': {name: sha(data) for name, data in sorted(control.items())},
    }, indent=2) + '\n').encode()
    overlay = archive(project / 'dist/pes13-perf41-control-overlay.zip', control)
    result = {'main': main_package, 'control': overlay}
    (work / 'packages.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
