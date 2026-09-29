"""Hash-checked package inputs for FEXTendo runtime updates."""
from pathlib import Path, PurePosixPath
import hashlib, json, zipfile
from nro_assets import inspect_nro
ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'switch/pes13-fex/'
NRO = PREFIX + 'pes13-fex.nro'
FEX = PREFIX + 'drive_c/windows/system32/libwow64fex.dll'
CHECKS = ('launcher', 'cores', 'gap', 'balance', 'yield', 'resume', 'pipeline',
          'jit-log', 'unwind', 'memory', 'budget', 'short-trace', 'dxvk-core3', 'polling')
EXTRA_CHECKS = ('jit-metrics', 'jit-metadata', 'dispatch-cache', 'lookup-hash')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def enc(value):
    return (json.dumps(value, indent=2) + '\n').encode()


def read(path):
    return json.loads(path.read_text())


def checked(path, expected):
    data = path.read_bytes()
    if sha(data) != expected:
        raise ValueError('Hash mismatch: ' + str(path))
    return data


def safe_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name or not path.parts:
        raise ValueError('Unsafe archive member: ' + name)
    return path


def verified_zip(path, expected):
    checked(path, expected)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read('manifest.json'))
        if archive.testzip() or len(names) != len(set(names)):
            raise ValueError('Invalid archive: ' + str(path))
        if set(names) != set(manifest['files']) | {'manifest.json'}:
            raise ValueError('Invalid archive inventory: ' + str(path))
        files = {}
        for name, digest in manifest['files'].items():
            safe_name(name)
            data = archive.read(name)
            if sha(data) != digest:
                raise ValueError('Invalid member hash: ' + name)
            files[name] = data
        return files, manifest


def delta(before, after):
    return sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))


def add_sources(files, sources, mapping, prefix=''):
    for name, digest in mapping.items():
        name = prefix + name
        safe_name(name)
        files['source/' + name] = checked(ROOT / name, digest)
        sources.add(name)
