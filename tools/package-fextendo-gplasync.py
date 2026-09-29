"""Package upstream GPLAsync 2.7.1-1 for the existing FEXTendo core3 runtime."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import zipfile

import pefile

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'local/fex3/gplasync-2.7.1-trial'
SAREK = ROOT / 'local/fex3/sarek-trial'
PREFIX = 'switch/pes13-fex/'
DLLS = ('drive_c/PES13/d3d9.dll', 'drive_c/dxvk/d3d9.dll')
CONFIGS = ('drive_c/PES13/dxvk.conf', 'launcher/presets/dxvk.conf')
RELEASE_COMMIT = '209a3069a19d13efb019e111f27114c185e86092'
DXVK_COMMIT = 'c3dd74be6baec53786d4e064a572185b70347a17'
ARCHIVE_SHA = '590050b88be7b156cf641abe762e1ad47ebbe828f7f0edb2970aa4716ee3af6d'
DLL_SHA = 'a2cd6841e102f37189527c118ec416fa5071ac4d3120762973d9a0c6c5fd067e'
SOURCE_SHA = '9591f43bb5d7fe81213f784061c2a2180912b718665e410dd996b39eff92cb0b'
PARENT_SHA = '2e4ea64fd68d5fde452474e40d5e416760b4ae0233814d5805df4c33634a724e'
PATCHES = {
    'dxvk-gplasync-2.7.1-1.patch': '848956793ada245a94a14b930f1d24b5545d7214255df90d02ef2eee831280b9',
    'global-dxvk.conf.patch': '750baef9712fc8c6813d189a94206ec2783590c02ed6be9198869f733035f040',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked(path, expected):
    data = path.read_bytes()
    if sha(data) != expected:
        raise ValueError('Hash mismatch: ' + str(path))
    return data


def enc(value):
    return (json.dumps(value, indent=2) + '\n').encode()


def options(data):
    values = {}
    for line in data.decode().splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        key, value = (part.strip() for part in line.split('=', 1))
        if key in values:
            raise ValueError('Duplicate option: ' + key)
        values[key] = value.strip('"')
    return values


def main():
    output = ROOT / 'dist/pes13-fextendo-dxvk-gplasync-2.7.1-v1.zip'
    folder = output.with_suffix('')
    if output.exists() or folder.exists():
        raise FileExistsError('Existing artifact protected')
    parent = ROOT / 'dist/pes13-fextendo-sarek-1.13.0-v2.zip'
    checked(parent, PARENT_SHA)
    with zipfile.ZipFile(parent) as z:
        parent_manifest = json.loads(z.read('manifest.json'))
        runtime = z.read('evidence/runtime-build.json')
        old_dll = z.read('rollback-dxvk311/' + PREFIX + DLLS[0])
        old_config = z.read('rollback-dxvk311/' + PREFIX + CONFIGS[0])
        if sha(old_dll) != '265888c31ca78dffa290c39cb7e50bfb02762590e41927906e46fb32f01497fa':
            raise ValueError('Rollback renderer mismatch')
        for path in DLLS:
            if z.read('rollback-dxvk311/' + PREFIX + path) != old_dll:
                raise ValueError('Rollback renderer copies differ')
        for path in CONFIGS:
            if z.read('rollback-dxvk311/' + PREFIX + path) != old_config:
                raise ValueError('Rollback config copies differ')

    release = json.loads((WORK / 'upstream-release.json').read_text())
    tag = json.loads((WORK / 'upstream-tag.json').read_text())
    if release['tag_name'] != 'v2.7.1-1' or release['commit']['id'] != RELEASE_COMMIT or tag['commit']['id'] != RELEASE_COMMIT:
        raise ValueError('GPLAsync release/tag mismatch')
    if json.loads((WORK / 'upstream-dxvk-commit.json').read_text())['sha'] != DXVK_COMMIT:
        raise ValueError('DXVK commit mismatch')
    metadata = json.loads((WORK / 'release-file-metadata.json').read_text())
    if metadata['x-gitlab-content-sha256'] != ARCHIVE_SHA:
        raise ValueError('GitLab asset digest mismatch')
    checked(WORK / 'dxvk-gplasync-v2.7.1-1.tar.gz', ARCHIVE_SHA)
    with tarfile.open(WORK / 'dxvk-gplasync-v2.7.1-1.tar.gz') as tar:
        dll = tar.extractfile('dxvk-gplasync-v2.7.1-1/x32/d3d9.dll').read()
    if sha(dll) != DLL_SHA:
        raise ValueError('Unmodified upstream DLL mismatch')
    with pefile.PE(data=dll) as pe:
        if pe.FILE_HEADER.Machine != 0x14c or pe.OPTIONAL_HEADER.Magic != 0x10b:
            raise ValueError('PE32 x86 renderer required')
        if not {b'Direct3DCreate9', b'Direct3DCreate9Ex'} <= {s.name for s in pe.DIRECTORY_ENTRY_EXPORT.symbols}:
            raise ValueError('D3D9 exports missing')
    for marker in (b'v2.7.1-1-gplasync', b'dxvk.enableAsync', b'DXVK_ASYNC', b'dxvk.numCompilerThreads', b'SetThreadDescription'):
        if marker not in dll:
            raise ValueError('Missing binary marker: ' + repr(marker))

    checked(WORK / 'dxvk-source-v2.7.1.tar.gz', SOURCE_SHA)
    for name, expected in PATCHES.items():
        checked(WORK / name, expected)
    with tempfile.TemporaryDirectory() as temp:
        with tarfile.open(WORK / 'dxvk-source-v2.7.1.tar.gz') as tar:
            tar.extractall(temp, filter='data')
            source = Path(temp) / tar.getnames()[0]
        patch_outputs = []
        for name in PATCHES:
            proc = subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(WORK / name)],
                                  cwd=source, check=True, capture_output=True, text=True)
            patch_outputs.append(proc.stdout)
        source_hashes = {p.relative_to(source).as_posix(): sha(p.read_bytes())
                         for p in sorted((source / 'src').rglob('*')) if p.is_file()}
        license_bytes = (source / 'LICENSE').read_bytes()
        option_source = (source / 'src/dxvk/dxvk_options.cpp').read_text() + (source / 'src/d3d9/d3d9_options.cpp').read_text()
        graphics = (source / 'src/dxvk/dxvk_graphics.cpp').read_text()
        if 'async && m_device->config().enableAsync && env::getEnvVar("DXVK_ASYNC") != "0"' not in graphics:
            raise ValueError('Async source path changed')
        # Small literal strings can be embedded as instruction immediates, so
        # validate this name in source rather than requiring a DLL string blob.
        if 'env::setThreadName("dxvk-cs")' not in (source / 'src/dxvk/dxvk_cs.cpp').read_text():
            raise ValueError('Command-stream thread name changed')

    config = (ROOT / 'config/fextendo/gplasync-2.7.1.conf').read_bytes()
    current = options(config)
    if current != {**options(old_config), 'dxvk.enableAsync': 'True'}:
        raise ValueError('Expected baseline options plus explicit async only')
    if len(config) >= 1024 or current['d3d9.maxFrameRate'] != '-1':
        raise ValueError('Config size/limiter mismatch')
    if any('"' + key + '"' not in option_source for key in current):
        raise ValueError('Unsupported config option')
    subprocess.run([sys.executable, '-B', str(ROOT / 'tests/fextendo_gplasync_limiter.py')],
                   check=True, capture_output=True, text=True)
    regression = (WORK / 'limiter-regression.json').read_bytes()
    if not json.loads(regression)['passed']:
        raise ValueError('Limiter test failed')

    # Import-stage DLLs were obtained from the pinned Wine release; verify them
    # before checking the new renderer against the same baseline environment.
    inputs = json.loads((SAREK / 'wine-import-inputs.json').read_text())
    stage = WORK / 'import-stage'
    for name, digest in inputs['files'].items():
        checked(stage / name, digest)
    with pefile.PE(str(stage / 'drive_c/windows/syswow64/kernel32.dll')) as pe:
        if b'SetThreadDescription' not in {s.name for s in pe.DIRECTORY_ENTRY_EXPORT.symbols}:
            raise ValueError('Wine thread-name export missing')
    (stage / 'drive_c/PES13/d3d9.dll').write_bytes(dll)
    report = WORK / 'imports-gplasync.json'
    proc = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/check_payload.py'),
                           str(stage), '--entry', 'd3d9.dll', '--dxvk', '--output', str(report)],
                          capture_output=True, text=True)
    if proc.returncode not in (0, 1):
        raise RuntimeError(proc.stderr)
    result = json.loads(report.read_text())
    baseline = json.loads((SAREK / 'imports-dxvk311.json').read_text())
    if any(not row.get('deferred', False) for row in result['issues']):
        raise ValueError('Required imports unresolved')
    if {json.dumps(r, sort_keys=True) for r in result['issues']} - {json.dumps(r, sort_keys=True) for r in baseline['issues']}:
        raise ValueError('New deferred imports versus DXVK 3.1.1')

    files = {}
    for destination, payload, cfg in (('', dll, config), ('rollback-dxvk311/', old_dll, old_config)):
        for path in DLLS:
            files[destination + PREFIX + path] = payload
        for path in CONFIGS:
            files[destination + PREFIX + path] = cfg
    files['README.md'] = (ROOT / 'docs/FEXTENDO-GPLASYNC-2.7.1-TRIAL.md').read_bytes()
    files['FEXTENDO-SAREK-NONE-RESULT.md'] = (ROOT / 'docs/FEXTENDO-SAREK-NONE-RESULT.md').read_bytes()
    files['THIRD_PARTY.md'] = (ROOT / 'THIRD_PARTY.md').read_bytes()
    files['licenses/DXVK-LICENSE.txt'] = license_bytes
    files['upstream/README.md'] = (WORK / 'upstream-README.md').read_bytes()
    files['upstream/build-gplasync.sh'] = (WORK / 'upstream-build-gplasync.sh').read_bytes()
    for name in PATCHES:
        files['upstream/patches/' + name] = (WORK / name).read_bytes()
    for name in ('upstream-release.json', 'upstream-tag.json', 'upstream-dxvk-commit.json',
                 'upstream-dxvk-tag-ref.json', 'release-file-metadata.json', 'imports-gplasync.json'):
        files['evidence/' + name] = (WORK / name).read_bytes()
    files['evidence/limiter-regression.json'] = regression
    files['evidence/runtime-build.json'] = runtime
    files['evidence/source-hashes.json'] = enc(source_hashes)
    files['evidence/patch-application.txt'] = '\n'.join(patch_outputs).encode()
    files['evidence/wine-import-inputs.json'] = (SAREK / 'wine-import-inputs.json').read_bytes()
    files['evidence/imports-dxvk311.json'] = (SAREK / 'imports-dxvk311.json').read_bytes()
    files['evidence/sarek-none-result.json'] = (ROOT / 'local/fex3/review-sarek-none-88a97a52e3/finding.json').read_bytes()
    files['source/package-fextendo-gplasync.py'] = Path(__file__).read_bytes()
    for name in ('fextendo_gplasync_limiter.py', 'fextendo_sarek_limiter.py'):
        files['source/' + name] = (ROOT / 'tests' / name).read_bytes()
    active = sorted(n for n in files if n.startswith('switch/'))
    if len(active) != 4:
        raise ValueError('Only two DLLs and two configs may be active')
    files['manifest.json'] = enc({
        'kind': 'fextendo-dxvk-gplasync-2.7.1-v1', 'hardware_tested': False,
        'renderer': 'DXVK-GPLAsync v2.7.1-1', 'async_enabled': True,
        'nro_included': False, 'configuration_ini_included': False,
        'requires_nro_sha256': parent_manifest['requires_nro_sha256'],
        'requires_fex_dll_sha256': parent_manifest['requires_fex_dll_sha256'],
        'release_commit': RELEASE_COMMIT, 'dxvk_commit': DXVK_COMMIT,
        'upstream_archive_sha256': ARCHIVE_SHA, 'd3d9_sha256': DLL_SHA,
        'dxvk_source_archive_sha256': SOURCE_SHA,
        'rollback_d3d9_sha256': sha(old_dll), 'active_files': active,
        'required_import_issues': 0, 'deferred_import_issues': len(result['issues']),
        'new_deferred_issues_vs_dxvk311': 0,
        'checks': ['release/tag and GitLab asset digest', 'unmodified PE32 D3D9 exports/version/async markers',
                   'upstream patches apply with zero fuzz', 'source recognizes every config option',
                   'baseline graphics config plus explicit async', 'ASan/UBSan limiter method tests',
                   'required Wine imports and thread naming export', 'ZIP inventory/bytes/CRC verified'],
        'files': {n: sha(data) for n, data in sorted(files.items())},
    })
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 29, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)
    with zipfile.ZipFile(output) as z:
        if z.testzip() or set(z.namelist()) != set(files):
            raise ValueError('ZIP inventory/CRC mismatch')
        for name, data in files.items():
            if z.read(name) != data:
                raise ValueError('ZIP content mismatch: ' + name)
    for name, data in files.items():
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    receipt = {'passed': True, 'path': str(output), 'bytes': output.stat().st_size,
               'sha256': sha(output.read_bytes()), 'hardware_tested': False,
               'd3d9_sha256': DLL_SHA, 'active_files': active}
    (WORK / 'package-v1.json').write_bytes(enc(receipt))
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
