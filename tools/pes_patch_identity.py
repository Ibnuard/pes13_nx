"""Apply the patch edition identity only to private, generated build sources.

The main/original source defaults and its release lock remain independent.
A patch-specific repair catalog is mandatory: the original catalog would
restore incompatible FEX/Wine files even if its install directory were renamed.
"""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / 'release/patch/channel.json'


def profile():
    value = json.loads(PROFILE_PATH.read_text())
    expected = {'channel': 'patch', 'branch': 'patch-release',
                'prefix': 'switch/pes13-patch-fex/', 'nro': 'pes13-patch-fex.nro',
                'memory_abi': 'fxtmem-v1', 'release_tag_prefix': 'patch-v',
                'make_latest': False}
    if any(value.get(k) != v for k, v in expected.items()):
        raise ValueError('Unexpected patch channel identity')
    return value


def title_id():
    p = profile()
    target = '/' + p['prefix'] + p['nro']
    raw = hashlib.sha256((target + '|fxtmem-v1|' + p['forwarder_tag']).encode()).digest()
    return 0x0500000000000000 | (int.from_bytes(raw[:8], 'little') & 0x00fffffffffff000)


def validate_catalog(data):
    text = data.decode('utf-8')
    if '#define FXR_PACKAGE_PREFIX "switch/pes13-patch-fex/"' not in text:
        raise ValueError('Patch repair catalog must use the patch archive prefix')
    url = re.search(r'^#define FXR_URL "([^"]+)"$', text, re.M)
    if not url or not re.fullmatch(
        r'https://github\.com/Ibnuard/pes13_nx/releases/download/runtime-patch-[A-Za-z0-9._-]+/'
        r'[A-Za-z0-9._-]+\.zip', url[1]
    ):
        raise ValueError('Patch build requires its own pinned runtime-patch repair catalog')
    for key in ('FXR_CATALOG_ID', 'FXR_ARCHIVE_SHA'):
        if not re.search(r'^#define ' + key + r' "[0-9a-f]{64}"$', text, re.M):
            raise ValueError('Missing patch repair hash: ' + key)
    if not re.search(r'^#define FXR_ARCHIVE_SIZE [1-9][0-9]*ull$', text, re.M):
        raise ValueError('Missing patch repair size')
    if 'drive_c/windows/system32/libwow64fex.dll' not in text:
        raise ValueError('Patch repair catalog does not cover FEX')
    return url[1]


def apply(source, feature, catalog, version):
    """Call after LW patches, before hashing/compiling the isolated build tree."""
    p = profile()
    if not re.fullmatch(r'\d+\.\d+\.\d+-patch\d+', version):
        raise ValueError('Expected an explicit patch runtime version')
    data = catalog.read_bytes()
    validate_catalog(data)
    source, feature = source.resolve(), feature.resolve()
    # This helper must never rewrite the checked-out originals in src/.
    for folder in (source, feature):
        if folder == ROOT or folder == (ROOT / 'src') or (ROOT / 'src') in folder.parents:
            raise ValueError('Patch identity must be applied to an isolated generated tree')
    changed = {}
    for folder in (source, feature):
        for path in folder.rglob('*'):
            if path.suffix not in ('.c', '.h', '.cpp', '.hpp', '.S', '.inc') or not path.is_file():
                continue
            before = path.read_bytes()
            after = before.replace(b'switch/pes13-fex', b'switch/pes13-patch-fex')
            if path == source / 'wine-nx-probe/source/runtime.c':
                after, count = re.subn(rb'#define FX_APP_VERSION "0\.3\.9-lw\d+"',
                                      ('#define FX_APP_VERSION "'+version+'"').encode(), after)
                if count != 1:
                    raise ValueError('Patch identity requires a prepared LW runtime')
            if path.name == 'fextendo_ui.h':
                after = after.replace(b'"PES13"', b'"PES13 Patch"')
                after = after.replace(b'"Starting PES13"', b'"Starting PES13 Patch"')
            if path.name == 'fextendo_launch_memory.h':
                after = after.replace(b'PES13 Low Window HOME tile', b'PES13 Patch HOME tile')
            if after != before:
                if path.is_symlink() or not path.resolve().is_relative_to(folder):
                    raise ValueError('Refusing to change source through a symlink: ' + str(path))
                path.write_bytes(after)
                changed[str(path)] = hashlib.sha256(after).hexdigest()
    (feature / 'fextendo_runtime_catalog.h').write_bytes(data)
    changed[str(feature / 'fextendo_runtime_catalog.h')] = hashlib.sha256(data).hexdigest()
    runtime = source / 'wine-nx-probe/source/runtime.c'
    if b'switch/pes13-patch-fex' not in runtime.read_bytes():
        raise ValueError('Runtime root was not relocated')
    return {'channel': p['channel'], 'profile': p, 'title_id': f'{title_id():016x}',
            'catalog_sha256': hashlib.sha256(data).hexdigest(), 'changed': changed}
