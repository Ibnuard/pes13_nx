"""Verify and package the unmodified Sarek release, NONE control and DXVK rollback."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import zipfile

import pefile

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'local/fex3/sarek-trial'
PREFIX = 'switch/pes13-fex/'
SAREK_COMMIT = '37f397e142b977a343e920dbc4c7bf7ed2c63a81'
SAREK_ARCHIVE = 'b42d8f2edeb5ed53d1e0009e17bcd765f53c1ac0fda6c936a76b70b2c289dcf8'
SAREK_DLL = '0c9d2236aa507ff23761d24382e44ea47512d9e21a01c2722cf3a2bc03dfcd04'
OLD_ARCHIVE = '40565b4a724aadc4433fa4e010b4b23916d9b1f1baeee64e17186db94f54e608'
OLD_DLL = '265888c31ca78dffa290c39cb7e50bfb02762590e41927906e46fb32f01497fa'
BASE_ARCHIVE = '5d44615d0315a1dd8dd5562f13c42e695c82887c3717dd00001054c8ea2f4ea3'
FEX_DLL = 'a8fc15d13e9f0e6443ccffc8974018bf3167aa8e2844c76cb2fb78e3c1d28e92'
DLL_PATHS = ('drive_c/PES13/d3d9.dll', 'drive_c/dxvk/d3d9.dll')
CONFIG_PATHS = ('drive_c/PES13/dxvk.conf', 'launcher/presets/dxvk.conf')


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
        line = re.split(r'[#;]', line, maxsplit=1)[0].strip()
        if not line or line.startswith('['):
            continue
        key, value = (part.strip() for part in line.split('=', 1))
        if key in values:
            raise ValueError('Duplicate option: ' + key)
        values[key] = value.strip('"')
    return values


def main():
    archive = ROOT / 'dist/pes13-fextendo-sarek-1.13.0-v2.zip'
    fix_archive = ROOT / 'dist/pes13-fextendo-sarek-loading-fix-v2.zip'
    folder = archive.with_suffix('')
    if archive.exists() or folder.exists() or fix_archive.exists():
        raise FileExistsError('Existing artifact protected')
    checked(ROOT / 'dist/pes13-fextendo-dxvk-core3-v1.zip', BASE_ARCHIVE)
    with zipfile.ZipFile(ROOT / 'dist/pes13-fextendo-dxvk-core3-v1.zip') as z:
        runtime = json.loads(z.read('evidence/runtime/runtime-build.json'))
        if sha(z.read(PREFIX + 'pes13-fex.nro')) != runtime['nro_sha256']:
            raise ValueError('Baseline NRO hash')
    checked(ROOT / 'local/fex3/dxvk-core3/module/libwow64fex.dll', FEX_DLL)
    checked(WORK / 'dxvk-sarek-1.13.0.tar.gz', SAREK_ARCHIVE)
    checked(WORK / 'dxvk-3.1.1.tar.gz', OLD_ARCHIVE)
    with tarfile.open(WORK / 'dxvk-sarek-1.13.0.tar.gz') as tar:
        sarek = tar.extractfile('dxvk-sarek-1.13.0/build/x32/d3d9.dll').read()
        license_sarek = tar.extractfile('dxvk-sarek-1.13.0/LICENSE').read()
    with tarfile.open(WORK / 'dxvk-3.1.1.tar.gz') as tar:
        old = tar.extractfile('dxvk-3.1.1/x32/d3d9.dll').read()
    if sha(sarek) != SAREK_DLL or sha(old) != OLD_DLL:
        raise ValueError('Renderer payload hash')
    for data in (sarek, old):
        with pefile.PE(data=data) as pe:
            if pe.FILE_HEADER.Machine != 0x14c:
                raise ValueError('Renderer must be PE32 x86')
            exports = {s.name for s in pe.DIRECTORY_ENTRY_EXPORT.symbols}
            if not {b'Direct3DCreate9', b'Direct3DCreate9Ex'} <= exports:
                raise ValueError('D3D9 exports')
    for marker in (b'dxvk.shaderCompilationMethod', b'dxvk.numShaderCompilerThreads',
                   b'DXVK_STATE_CACHE_PATH', b'SetThreadDescription'):
        if marker not in sarek:
            raise ValueError('Missing release marker: ' + repr(marker))
    release = WORK / 'release/dxvk-sarek-1.13.0'
    source = WORK / 'source/pythonlover02-dxvk-sarek-37f397e'
    if json.loads((WORK / 'upstream-commit.json').read_text())['sha'] != SAREK_COMMIT:
        raise ValueError('Source pin')
    source_hashes = {}
    for path in sorted((source / 'src').rglob('*')):
        if not path.is_file():
            continue
        name = path.relative_to(source).as_posix()
        if path.read_bytes() != (release / name).read_bytes():
            raise ValueError('Release source differs from tag: ' + name)
        source_hashes[name] = sha(path.read_bytes())

    inputs = json.loads((WORK / 'wine-import-inputs.json').read_text())
    stage = WORK / 'import-stage'
    for name, expected in inputs['files'].items():
        checked(stage / name, expected)
    with pefile.PE(str(stage / 'drive_c/windows/syswow64/kernel32.dll')) as pe:
        if b'SetThreadDescription' not in {s.name for s in pe.DIRECTORY_ENTRY_EXPORT.symbols}:
            raise ValueError('Wine thread naming export')
    import_reports = {}
    for label, data in (('sarek', sarek), ('dxvk311', old)):
        (stage / 'drive_c/PES13/d3d9.dll').write_bytes(data)
        report = WORK / ('imports-' + label + '.json')
        proc = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/check_payload.py'),
                               str(stage), '--entry', 'd3d9.dll', '--dxvk',
                               '--output', str(report)], capture_output=True, text=True)
        if proc.returncode not in (0, 1):
            raise RuntimeError(proc.stdout + proc.stderr)
        result = json.loads(report.read_text())
        if any(not row.get('deferred', False) for row in result['issues']):
            raise ValueError('Unresolved required imports: ' + label)
        import_reports[label] = result
    def issue_set(label):
        return {json.dumps(row, sort_keys=True) for row in import_reports[label]['issues']}
    new_deferred = issue_set('sarek') - issue_set('dxvk311')
    if new_deferred:
        raise ValueError('New deferred dependency issues: ' + repr(new_deferred))

    before = (ROOT / 'dist/cache-trial-v1/switch/pes13-fex/configuration.ini').read_bytes()
    off, count = re.subn(rb'(?m)^(fex_diskcache\s*=\s*)1\s*$', rb'\g<1>0', before)
    if count != 1:
        raise ValueError('Expected one existing disk-cache ON option')
    off = off.rstrip(b'\r\n') + b'\n'
    old_options, off_options = options(before), options(off)
    if {k for k in old_options.keys() | off_options.keys()
            if old_options.get(k) != off_options.get(k)} != {'fex_diskcache'}:
        raise ValueError('Unexpected INI delta')
    if off_options['fex_diskcache'] != '0' or off_options['run_guest_tests'] != '0':
        raise ValueError('Trial INI must disable disk cache and launch game')
    with zipfile.ZipFile(ROOT / 'dist/pes13-fextendo-v3.2.zip') as z:
        old_config = z.read(PREFIX + CONFIG_PATHS[0])
        if old_config != z.read(PREFIX + CONFIG_PATHS[1]):
            raise ValueError('Baseline launcher template differs')
    config = (ROOT / 'config/fextendo/sarek-1.13.0.conf').read_bytes()
    previous, current = options(old_config), options(config)
    changed = {k for k, v in previous.items() if current.get(k) != v}
    if changed != {'d3d9.maxFrameRate'} or previous['d3d9.maxFrameRate'] != '-1' or current['d3d9.maxFrameRate'] != '0':
        raise ValueError('Expected only Sarek limiter compatibility correction')
    subprocess.run([sys.executable, '-B', str(ROOT / 'tests/fextendo_sarek_limiter.py')],
                   check=True, capture_output=True, text=True)
    limiter_bytes = (WORK / 'limiter-regression.json').read_bytes()
    limiter = json.loads(limiter_bytes)
    if not limiter.get('passed'):
        raise ValueError('Limiter regression failed')
    expected = {'dxvk.numShaderCompilerThreads': '1', 'dxvk.enableStateCache': 'True',
                'dxvk.shaderCompilationMethod': 'dyasync', 'dxvk.framePace': 'max-frame-latency'}
    if {k: v for k, v in current.items() if k not in previous} != expected:
        raise ValueError('Unexpected Sarek options')
    if b'd3d9.presentInterval = 1\n' not in config or len(config) >= 1024:
        raise ValueError('Launcher preset config contract')
    control = config.replace(b'"dyasync"', b'"none"')
    if options(control) != {**current, 'dxvk.shaderCompilationMethod': 'none'}:
        raise ValueError('NONE control delta')

    files = {}
    for destination, dll, conf in (('', sarek, config), ('rollback-dxvk311/', old, old_config)):
        for name in DLL_PATHS:
            files[destination + PREFIX + name] = dll
        for name in CONFIG_PATHS:
            files[destination + PREFIX + name] = conf
        files[destination + PREFIX + 'configuration.ini'] = off
        files[destination + PREFIX + 'fex_diskcache'] = b'0\n'
    for name in CONFIG_PATHS:
        files['control-none/' + PREFIX + name] = control
    files['README.md'] = (ROOT / 'docs/FEXTENDO-SAREK-TRIAL.md').read_bytes()
    files['FEXTENDO-CACHE-TRIAL-RESULT.md'] = (ROOT / 'docs/FEXTENDO-CACHE-TRIAL-RESULT.md').read_bytes()
    files['FEXTENDO-SAREK-TRIAL.md'] = files['README.md']
    files['FEXTENDO-SAREK-LOADING-FIX.md'] = (ROOT / 'docs/FEXTENDO-SAREK-LOADING-FIX.md').read_bytes()
    files['THIRD_PARTY.md'] = (ROOT / 'THIRD_PARTY.md').read_bytes()
    files['licenses/DXVK-Sarek-LICENSE.txt'] = license_sarek
    files['licenses/DXVK-LICENSE.txt'] = (ROOT / 'licenses/DXVK-LICENSE.txt').read_bytes()
    for name in ('cache-comparison.json', 'imports-sarek.json', 'imports-dxvk311.json',
                 'wine-import-inputs.json', 'upstream-commit.json'):
        files['evidence/' + name] = (WORK / name).read_bytes()
    releases = json.loads((WORK / 'upstream-releases.json').read_text())
    files['evidence/upstream-release.json'] = enc(next(r for r in releases if r['tag_name'] == 'v1.13.0'))
    files['evidence/runtime-build.json'] = enc(runtime)
    files['evidence/configuration-before.ini'] = before
    files['evidence/source-hashes.json'] = enc(source_hashes)
    files['evidence/limiter-regression.json'] = limiter_bytes
    files['source/fextendo_sarek_limiter.py'] = (ROOT / 'tests/fextendo_sarek_limiter.py').read_bytes()
    files['source/package-fextendo-sarek.py'] = Path(__file__).read_bytes()
    files['manifest.json'] = enc({
        'kind': 'fextendo-sarek-1.13.0-v2', 'hardware_tested': False,
        'renderer': 'DXVK-Sarek 1.13.0', 'shader_method': 'dyasync', 'fex_diskcache': False,
        'nro_included': False, 'requires_nro_sha256': runtime['nro_sha256'],
        'requires_fex_dll_sha256': FEX_DLL, 'sarek_commit': SAREK_COMMIT,
        'sarek_archive_sha256': SAREK_ARCHIVE, 'sarek_d3d9_sha256': SAREK_DLL,
        'rollback_d3d9_sha256': OLD_DLL, 'configuration_input_sha256': sha(before),
        'checks': ['official archive and PE32 payload hashes', 'tag/release source agreement',
                   'PE32 machine and D3D9 exports', 'required imports resolved for both renderers',
                   'no new deferred import issues versus baseline', 'Wine thread-name export',
                   'INI changes disk-cache only', 'Sarek limiter corrected -1 to 0; other old graphics options retained',
                   'ASan/UBSan upstream-method reproduction of 1 FPS and disabled-limiter control',
                   'launcher preset template matches active config', 'NONE control changes one option',
                   'rollback restores DXVK 3.1.1 and keeps FEX disk cache OFF'],
        'deferred_import_issues': {k: len(v['issues']) for k, v in import_reports.items()},
        'active_files': sorted(n for n in files if n.startswith('switch/')),
        'files': {n: sha(data) for n, data in sorted(files.items())},
    })
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 29, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() or set(z.namelist()) != set(files):
            raise ValueError('Final archive inventory')
        for name, data in files.items():
            if z.read(name) != data:
                raise ValueError('Final archive member: ' + name)
    for name, data in files.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    # Existing Sarek installations only need the two corrected configs.
    # Keep v1 immutable; verify this is the only active semantic change.
    previous_zip = ROOT / 'dist/pes13-fextendo-sarek-1.13.0-v1.zip'
    checked(previous_zip, '9d786440b951a7d9a03533fc3b9899d0f02b68747132e7b48b9e07ee5f180e60')
    with zipfile.ZipFile(previous_zip) as z:
        for name in CONFIG_PATHS:
            previous_options = options(z.read(PREFIX + name))
            if current != {**previous_options, 'd3d9.maxFrameRate': '0'}:
                raise ValueError('Small patch must change limiter only')
        for name in (*DLL_PATHS, 'configuration.ini', 'fex_diskcache'):
            if z.read(PREFIX + name) != files[PREFIX + name]:
                raise ValueError('Small patch prerequisites changed')
    fix_files = {PREFIX + name: config for name in CONFIG_PATHS}
    fix_files['README.md'] = files['FEXTENDO-SAREK-LOADING-FIX.md']
    fix_files['evidence/limiter-regression.json'] = limiter_bytes
    fix_files['manifest.json'] = enc({
        'kind': 'sarek-loading-fix-v2', 'hardware_tested': False,
        'requires_installed_sarek_d3d9_sha256': SAREK_DLL,
        'semantic_delta': {'d3d9.maxFrameRate': {'before': '-1', 'after': '0'}},
        'files': {n: sha(data) for n, data in sorted(fix_files.items())},
    })
    with zipfile.ZipFile(fix_archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(fix_files.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 29, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)
    with zipfile.ZipFile(fix_archive) as z:
        if z.testzip() or set(z.namelist()) != set(fix_files):
            raise ValueError('Fix ZIP inventory')
        for name, data in fix_files.items():
            if z.read(name) != data:
                raise ValueError('Fix ZIP member: ' + name)
    result = {'passed': True, 'path': str(archive), 'bytes': archive.stat().st_size,
              'sha256': sha(archive.read_bytes()), 'hardware_tested': False,
              'sarek_sha256': SAREK_DLL, 'rollback_sha256': OLD_DLL,
              'small_fix': {'path': str(fix_archive), 'bytes': fix_archive.stat().st_size,
                            'sha256': sha(fix_archive.read_bytes())}}
    (WORK / 'package-v2.json').write_bytes(enc(result))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
