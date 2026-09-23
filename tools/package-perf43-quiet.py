"""Create a config-only PERF43 control that removes intrusive CPU sampling."""
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
import hashlib
import io
import json


project = Path(__file__).resolve().parents[1]
prefix = 'switch/pes13-nx/'
source = project / 'dist/pes13-perf43-match-probe-r2.zip'
target = project / 'dist/pes13-perf43-quiet-overlay.zip'
sha = lambda data: hashlib.sha256(data).hexdigest()


def main():
    with ZipFile(source) as archive:
        assert archive.testzip() is None
        manifest = json.loads(archive.read('PERF43-manifest.json'))
        nro = archive.read(prefix + 'pes13-nx.nro')
        assert sha(nro) == manifest['nro_sha256']
        assert manifest['execution_policy_unchanged']
        files = {}
        for suffix in ('configuration.ini', 'drive_c/PES13/pes2013.wine-nx.txt'):
            name = prefix + suffix
            original = archive.read(name)
            assert sha(original) == manifest['files'][name]
            assert original.count(b'profile=1') == 1
            updated = original.replace(b'profile=1', b'profile=0')
            assert updated != original and updated.count(b'profile=0') == 1
            files[name] = updated

    control = {
        'variant': 'PERF43 same-NRO quiet control',
        'requires_nro_sha256': sha(nro),
        'contains_nro': False,
        'changed_runtime_files': sorted(files),
        'hardware_tested': False,
        'performance_improvement_claimed': False,
        'files': {name: sha(data) for name, data in sorted(files.items())},
    }
    files['PERF43-quiet-manifest.json'] = (json.dumps(control, indent=2) + '\n').encode()
    files['PERF43-RESULT.md'] = (project / 'docs/PERF43-RESULT.md').read_bytes()
    buffer = io.BytesIO()
    with ZipFile(buffer, 'w', ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            assert not name.startswith('/') and '..' not in Path(name).parts
            info = ZipInfo(name, (2026, 9, 24, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, data)
    payload = buffer.getvalue()
    if target.exists():
        assert target.read_bytes() == payload, 'Refusing to overwrite changed archive'
    else:
        with target.open('xb') as stream:
            stream.write(payload)
    with ZipFile(target) as archive:
        assert archive.testzip() is None
        assert archive.namelist() == sorted(files)
        assert all(archive.read(name) == data for name, data in files.items())
        assert not any(name.endswith(('.nro', '.exe', '.dll', '.dat', '.reg', '.log'))
                       for name in archive.namelist())
    print(json.dumps({'path': str(target), 'sha256': sha(payload),
                      'bytes': len(payload), 'requires_nro_sha256': sha(nro)}, indent=2))


if __name__ == '__main__':
    main()
