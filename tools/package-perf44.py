"""Package the verified PERF44 diagnostic NRO with the stable PERF42 policy."""
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
import hashlib
import io
import json

project = Path(__file__).resolve().parents[1]
work = project / 'local/perf44'
prefix = 'switch/pes13-nx/'
source = project / 'dist/pes13-perf42-startup-guard.zip'
target = project / 'dist/pes13-perf44-event-pipeline.zip'
sha = lambda data: hashlib.sha256(data).hexdigest()


def main():
    report = json.loads((work / 'verification.json').read_text())
    for key in ('source_restored', 'same_game_emitters_as_perf42',
                'same_unix_bootguard_as_perf42',
                'vulkan_objects_both_instrumented'):
        assert report[key], key
    assert report['linked_span_calls'] >= 8
    assert report['nro_metadata']['title'] == 'PES13-NX PERF44 PIPELINE'
    assert report['hardware_tested'] is False

    with ZipFile(source) as archive:
        assert archive.testzip() is None
        old_manifest = json.loads(archive.read('PERF42-manifest.json'))
        files = {name: archive.read(name) for name in archive.namelist()
                 if name != 'PERF42-manifest.json'}
    assert set(files) == set(old_manifest['files'])
    assert all(sha(data) == old_manifest['files'][name]
               for name, data in files.items())
    files = {name: data for name, data in files.items()
             if not (name.startswith('PERF') and name.endswith('.md'))}
    old_nro = files[prefix + 'pes13-nx.nro']
    nro = (work / 'payload' / prefix / 'pes13-nx.nro').read_bytes()
    assert sha(nro) == json.loads((work / 'build.json').read_text())['nro_sha256']
    assert nro != old_nro
    files[prefix + 'pes13-nx.nro'] = nro
    files['PERF44.md'] = (project / 'docs/PERF44.md').read_bytes()

    config = files[prefix + 'configuration.ini']
    wine_config = files[prefix + 'drive_c/PES13/pes2013.wine-nx.txt']
    assert config.count(b'profile=0') == 1
    assert wine_config.count(b'profile=0') == 1
    assert config.count(b'perf42_startup_guard=1') == 1
    assert sum(name.endswith('.nro') for name in files) == 1
    assert not any('/users/' in name or name.lower().endswith(
        ('.exe', '.reg', '.dat', '.log')) for name in files)
    changed = [prefix + 'pes13-nx.nro']
    manifest = {
        'variant': 'PERF44 bounded CPU-side Vulkan stage diagnostic',
        'base': 'PERF42 startup guard and game policy',
        'nro_metadata': report['nro_metadata'],
        'nro_sha256': sha(nro),
        'changed_runtime_files': changed,
        'hardware_tested': False,
        'performance_improvement_claimed': False,
        'files': {name: sha(data) for name, data in sorted(files.items())},
    }
    files['PERF44-manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    buffer = io.BytesIO()
    with ZipFile(buffer, 'w', ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            assert not name.startswith('/') and '..' not in Path(name).parts
            info = ZipInfo(name, (2026, 9, 24, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, data)
    raw = buffer.getvalue()
    if target.exists():
        assert target.read_bytes() == raw, 'Refusing to overwrite changed archive'
    else:
        with target.open('xb') as output:
            output.write(raw)
    with ZipFile(target) as archive:
        assert archive.testzip() is None
        assert archive.namelist() == sorted(files)
        assert all(archive.read(name) == data for name, data in files.items())
    result = {'path': str(target), 'sha256': sha(raw), 'bytes': len(raw),
              'nro_sha256': sha(nro)}
    (work / 'package.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
