"""Package the checked v3.4 CPU candidate and native LSFG, never Lossless.dll."""
from pathlib import Path, PurePosixPath
import argparse
import gzip
import hashlib
import importlib.util
import io
import json
import subprocess
import tarfile
import tempfile
import zipfile

from nro_assets import inspect_nro

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'local/fex3/cpu-balance-v2'
BASE_NAME = 'pes13-fextendo-v3.3-renderers-jit128-v1.zip'
BASE_SHA = '620d709b221c422b65e45799b66dfa64cfb641fbbd6a5acc5b84f7832aa5a364'
LSFG_PIN = '8b0da2661c6f3473a7fccc8ba643880050e71642'
LSFG_PORT = '0fff003d388139829b303382b13c14c5344672b2'
PREFIX = 'switch/pes13-fex/'
NRO = PREFIX + 'pes13-fex.nro'
FEX = PREFIX + 'drive_c/windows/system32/libwow64fex.dll'
CHECKS = ('launcher', 'cores', 'gap', 'balance', 'yield', 'resume', 'pipeline',
          'jit-log', 'unwind', 'memory', 'budget', 'short-trace', 'dxvk-core3')
EXTRA_CHECKS = ('jit-metrics', 'jit-metadata', 'dispatch-cache', 'lookup-hash', 'lsfg-checks')
GUIDE = 'docs/FEXTENDO-V3.4-CPU-BALANCE.md'
AUDIT = 'docs/FEXTENDO-V3.4-PERFORMANCE-AUDIT.md'


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


def lsfg_source_bundle(files, prefix, runtime):
    work = prefix.parent
    receipt_path = work / 'build-manifest.json'
    receipt = read(receipt_path)
    if (receipt.get('commit') != LSFG_PIN or receipt.get('port_commit') != LSFG_PORT
            or receipt.get('fixed_x18') is not True
            or receipt.get('proprietary_payload_included') is not False
            or Path(receipt['prefix']).resolve() != prefix):
        raise ValueError('Unexpected LSFG build receipt')
    library = checked(prefix / 'lib/liblsfg-vk.a', receipt['library_sha256'])
    if (not runtime.get('lsfg') or runtime['lsfg_backend']['sha256'] != sha(library)
            or Path(runtime['lsfg_backend']['prefix']).resolve() != prefix):
        raise ValueError('Runtime is not linked to the checked LSFG backend')
    source = work / 'source'
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    if actual != LSFG_PIN:
        raise ValueError('Wrong LSFG source revision')
    port = ROOT / 'third_party/lsfg-horizon'
    patch = checked(port / 'horizon.patch', receipt['horizon_patch_sha256'])
    original = subprocess.check_output(['git', 'archive', '--format=tar', LSFG_PIN], cwd=source)
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=source).decode().split('\0')
    tracked = [name for name in tracked if name]
    # Prove the present sources equal the pinned revision plus the shipped patch.
    # Use a temporary extraction, never reset or modify the shared checkout.
    with tempfile.TemporaryDirectory(prefix='fextendo-lsfg-source-') as directory:
        root = Path(directory)
        with tarfile.open(fileobj=io.BytesIO(original)) as archive:
            for member in archive.getmembers():
                safe_name(member.name)
                if member.isdir():
                    continue
                if not member.isfile():
                    raise ValueError('Unexpected LSFG archive link/special file: ' + member.name)
                target = root / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
        subprocess.run(['git', 'apply', str(port / 'horizon.patch')],
                       cwd=root, check=True, capture_output=True)
        for name in tracked:
            safe_name(name)
            if (source / name).read_bytes() != (root / name).read_bytes():
                raise ValueError('LSFG working source differs from pinned patch: ' + name)
    files['upstream/lsfg-vk-' + LSFG_PIN + '.tar.gz'] = gzip.compress(original, mtime=0)
    files['licenses/LSFG-VK-GPL-3.0-or-later.md'] = (source / 'LICENSE.md').read_bytes()
    files['evidence/lsfg/build-manifest.json'] = receipt_path.read_bytes()
    files['evidence/lsfg/compiled-source-hashes.json'] = enc({
        name: sha((source / name).read_bytes()) for name in sorted(tracked)})
    files['upstream/LSFG-BUILD.md'] = (
        '# LSFG native backend source\n\n'
        f'Pinned upstream: https://git.lsfg-vk.dev/lsfg-vk-archive.git @ {LSFG_PIN}.\n'
        f'Horizon port reference: autorunhq/switch-dev @ {LSFG_PORT}.\n\n'
        'The tar.gz is the full unmodified pinned source. Apply the included\n'
        '`source/third_party/lsfg-horizon/horizon.patch`; the corresponding CMake\n'
        'files and NVK shaders are in the same directory. FEXTendo build recipe:\n'
        '`source/tools/build-fextendo-lsfg.py`. It preserves x18 for the Wine TEB.\n'
        'The native integration and runtime build recipe are included under\n'
        '`source/src/runtime/` and `source/tools/`. All modified Wine/FEX files\n'
        'listed by their build receipts are under `source/generated/`.\n\n'
        'LSFG-VK is GPL-3.0-or-later. Autorun presentation integration and the\n'
        'Cemu-NX-derived Horizon backend retain their notices and attribution.\n'
        'No proprietary Lossless.dll, extracted shader/model payload, or game\n'
        'data is distributed. The library is linked into the NRO, not installed\n'
        'as a separate SD file. See THIRD_PARTY.md for all project credits.\n'
    ).encode()
    return receipt, sha(receipt_path.read_bytes())


def collect(work, lsfg_prefix):
    base, baseline = verified_zip(ROOT / 'dist' / BASE_NAME, BASE_SHA)
    runtime = read(work / 'runtime/runtime-build.json')
    patches = read(work / 'runtime/wine-patches.json')
    module = read(work / 'module/build.json')
    old = json.loads(base['evidence/runtime/runtime-build.json'])
    for key in ('native_dependencies', 'ntdll_sha256', 'wow64_sha256', 'guest_sha256', 'toolchain_path'):
        if runtime[key] != old[key]:
            raise ValueError('Unexpected runtime dependency change: ' + key)
    for key, value in old.items():
        if isinstance(value, bool) and runtime.get(key) != value:
            raise ValueError('Unexpected build flag change: ' + key)
    previous = json.loads(base['evidence/runtime/wine-patches.json'])
    if patches['pe-source'] != previous['pe-source']:
        raise ValueError('Guest Wine changed')
    native_delta = delta(previous['native-source'], patches['native-source'])
    if native_delta != sorted(('wine-nx-probe/source/runtime.c', 'wine-nx-probe/CMakeLists.txt',
                               'dlls/win32u/vulkan.c')):
        raise ValueError('Unexpected native source delta: ' + repr(native_delta))
    old_module = json.loads(base['evidence/module/build.json'])
    adapter_delta = delta(old_module['adapter_sources'], module['adapter_sources'])
    if adapter_delta != ['tools/fex_horizon_patches.py']:
        raise ValueError('Unexpected FEX adapter delta: ' + repr(adapter_delta))
    old_fex = {e['path']: e['patched_sha256'] for e in
               json.loads(base['evidence/module/patches.json'])['files']}
    new_fex = {e['path']: e['patched_sha256'] for e in read(work / 'module/patches.json')['files']}
    fex_delta = delta(old_fex, new_fex)
    if fex_delta != sorted('FEXCore/Source/Interface/Core/' + name for name in
                          ('Dispatcher/Dispatcher.cpp', 'JIT/BranchOps.cpp', 'LookupCache.cpp', 'LookupCache.h')):
        raise ValueError('Unexpected FEX source delta: ' + repr(fex_delta))
    # Assets/profiles are the already verified v3.3 bundle; no user preferences.
    files = {name: data for name, data in base.items()
             if name.startswith(('licenses/', 'upstream/', 'switch/'))}
    files['evidence/baseline/v3.3-manifest.json'] = enc(baseline)
    files[NRO] = checked(work / 'runtime/payload/pes13-fex.nro', runtime['nro_sha256'])
    files[FEX] = checked(work / 'module/libwow64fex.dll', module['sha256'])
    elf = work / 'runtime/reference/pes13-fex.elf'
    checked(elf, runtime['native_elf_sha256'])
    metadata = inspect_nro(files[NRO], (ROOT / 'assets/fextendo-v3/nro-icon.jpg').read_bytes(),
                           expected_title='PES13 - FEXTendo', expected_version='0.3.5')
    if metadata != runtime['metadata'] or metadata['author'] != 'AndroSwitch Project':
        raise ValueError('NRO identity mismatch')
    spec = importlib.util.spec_from_file_location('stable', ROOT / 'tools/package-fex3-stability.py')
    stable = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stable)
    stable.verify_executable(elf, files[NRO])
    for marker in (b'pes13-fextendo-cpu-balance-v2', b'[FEX3-DXVKPOLICY]',
                   b'FEX_MAXINST=128\0', b'[LSFG]'):
        if marker not in files[NRO]:
            raise ValueError('Missing NRO marker: ' + repr(marker))
    if b'index=rip-xor-rip16' not in files[FEX]:
        raise ValueError('Missing FEX hashed lookup marker')
    art = work / 'package/switch/pes13-fex/launcher'
    art_manifest = read(art / 'assets.json')
    for name, digest in art_manifest['files'].items():
        if Path(name).suffix in ('.rgba', '.bin', '.pcm'):
            if files[PREFIX + 'launcher/' + name] != checked(art / name, digest):
                raise ValueError('Tested artwork differs from package: ' + name)
    for name, data in files.items():
        if name.startswith(PREFIX + 'launcher/renderers/'):
            if (art / name.removeprefix(PREFIX + 'launcher/')).read_bytes() != data:
                raise ValueError('Tested renderer profile differs from package: ' + name)
    files['evidence/launcher-assets.json'] = enc(art_manifest)
    for flag, value in {'fex_dxvk_balance': 1, 'fex_auto_core3': 0,
                        'fex_jit_small': 1, 'fex_jit_large': 0}.items():
        files[PREFIX + flag] = f'{value}\n'.encode()
    for folder in ('control-core3/', 'rollback/'):
        files[folder + PREFIX + 'fex_dxvk_balance'] = b'0\n'
        files[folder + PREFIX + 'fex_dxvk_core3'] = b'1\n'
        files[folder + PREFIX + 'fex_auto_core3'] = b'0\n'
    files['rollback/' + NRO] = base[NRO]
    files['rollback/' + FEX] = base[FEX]
    files['rollback/' + PREFIX + 'fex_jit_small'] = b'1\n'
    files['rollback/' + PREFIX + 'fex_jit_large'] = b'0\n'
    files['control-lookup/' + FEX] = base[FEX]
    files['control-lookup/' + PREFIX + 'fex_dxvk_balance'] = b'1\n'
    sources = set()
    for mapping in (runtime['patch_sources'], module['adapter_sources']):
        add_sources(files, sources, mapping)
    add_sources(files, sources, runtime['adapter_sources'], 'src/fex/')
    for name in CHECKS:
        path = work / (name + '.json')
        report = read(path)
        if report.get('passed') is not True or report['native_elf_sha256'] != runtime['native_elf_sha256']:
            raise ValueError('Stale/failed runtime check: ' + name)
        if name == 'short-trace' and report['dll_sha256'] != module['sha256']:
            raise ValueError('Wrong trace module')
        if name == 'unwind' and report['fex_sha256'] != module['sha256']:
            raise ValueError('Wrong unwind module')
        add_sources(files, sources, report.get('source_hashes', report.get('source_sha256', {})))
        files['evidence/checks/' + name + '.json'] = path.read_bytes()
    jit = read(work / 'jit-metrics.json')
    if jit.get('passed') is not True or jit['runtime_source_sha256'] != patches['native-source']['wine-nx-probe/source/runtime.c']:
        raise ValueError('Stale JIT metrics check')
    add_sources(files, sources, jit['sources'], 'src/fex/')
    files['evidence/checks/jit-metrics.json'] = enc(jit)
    metadata_check = read(work / 'jit-metadata.json')
    if metadata_check.get('passed') is not True or metadata_check['dll_sha256'] != module['sha256']:
        raise ValueError('Stale metadata optimization check')
    checked(work / 'module/patches.json', metadata_check['patches_sha256'])
    add_sources(files, sources, metadata_check['source_hashes'])
    files['evidence/checks/jit-metadata.json'] = enc(metadata_check)
    for name in ('dispatch-cache', 'lookup-hash'):
        report = read(work / (name + '.json'))
        if (report.get('passed') is not True or report['dll_sha256'] != module['sha256']
                or report['before_sha256'] != old_module['sha256']):
            raise ValueError('Stale lookup check: ' + name)
        add_sources(files, sources, report['test_sources'], 'tests/')
        files['evidence/checks/' + name + '.json'] = enc(report)
    lsfg, lsfg_receipt_hash = lsfg_source_bundle(files, lsfg_prefix, runtime)
    lsfg_check = read(work / 'lsfg-checks.json')
    if (lsfg_check.get('passed') is not True
            or lsfg_check['native_elf_sha256'] != runtime['native_elf_sha256']
            or lsfg_check['backend_library_sha256'] != lsfg['library_sha256']
            or lsfg_check['backend_manifest_sha256'] != lsfg_receipt_hash):
        raise ValueError('Stale LSFG check')
    add_sources(files, sources, lsfg_check['source_hashes'])
    files['evidence/checks/lsfg-checks.json'] = enc(lsfg_check)
    # Keep every patched generated source, not only the delta from v3.3.
    fex_source = Path(module['dll']).parents[2] / 'source-horizon'
    for name, digest in new_fex.items():
        safe_name(name)
        files['source/generated/fex/' + name] = checked(fex_source / name, digest)
    wine_root = Path(runtime['native_source']).parent.parent
    for kind in ('native-source', 'pe-source'):
        for name, digest in patches[kind].items():
            safe_name(name)
            files['source/generated/wine/' + kind + '/' + name] = checked(wine_root / kind / name, digest)
    for part, names in [('runtime', ('runtime-build.json', 'wine-patches.json')),
                        ('module', ('build.json', 'patches.json'))]:
        for name in names:
            files['evidence/' + part + '/' + name] = (work / part / name).read_bytes()
    sources |= {GUIDE, AUDIT, 'tools/package-fextendo-v3.4.py', 'tools/build-fex-module.py',
                'tools/build-fextendo-lsfg.py', 'tests/fextendo_lsfg.py',
                'tests/fex_jit_latency.py', 'tests/run_fextendo_checks.py', 'tools/nro_assets.py',
                'tools/package-fex3-stability.py', 'assets/fextendo-v3/nro-icon.jpg'}
    for name in sources:
        files['source/' + name] = (ROOT / name).read_bytes()
    files['README.md'] = (ROOT / GUIDE).read_bytes()
    files['PERFORMANCE-AUDIT.md'] = (ROOT / AUDIT).read_bytes()
    files['THIRD_PARTY.md'] = (ROOT / 'THIRD_PARTY.md').read_bytes()
    active = sorted(name for name in files if name.startswith('switch/'))
    forbidden = ('configuration.ini', 'settings.dat', 'renderer-choice.txt', 'selected.txt',
                 'framegen.txt', 'frame-generation.txt', 'lsfg.txt', 'Lossless.dll',
                 'menu-sound.txt', 'background-music.txt', 'debug-timestamp.txt', 'last-played.txt')
    if any(name.endswith(forbidden) for name in active):
        raise ValueError('Package overwrites a user preference or includes Lossless.dll')
    if any(PurePosixPath(name).name.lower() == 'lossless.dll' for name in files):
        raise ValueError('Proprietary DLL must never be packaged')
    manifest = {'kind': 'fextendo-v3.4-cpu-balance-v2', 'hardware_tested': False,
        'stutter_fix_confirmed': False, 'version': '0.3.5', 'default_renderer': 'dxvk-3.1.1',
        'jit_candidate_maxinst': 128, 'dxvk_balancing_default': True,
        'lookup_index': 'rip-xor-rip16', 'lsfg_compiled': True, 'lsfg_default': False,
        'proprietary_payload_included': False,
        'requires': 'working FEXTendo v3.3 installation; same Wine/Mesa dependencies',
        'nro_sha256': runtime['nro_sha256'], 'native_elf_sha256': runtime['native_elf_sha256'],
        'fex_sha256': module['sha256'], 'native_changed': native_delta,
        'fex_adapter_changed': adapter_delta, 'fex_core_changed': fex_delta,
        'lsfg_backend_sha256': lsfg['library_sha256'], 'lsfg_source_commit': LSFG_PIN,
        'checks': list(CHECKS + EXTRA_CHECKS), 'active_files': active,
        'files': {name: sha(data) for name, data in sorted(files.items())}}
    return files, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=WORK)
    parser.add_argument('--lsfg-prefix', type=Path, default=ROOT / 'local/fex3/lsfg-build/install')
    parser.add_argument('--validate-only', action='store_true', help='Verify all evidence without creating an artifact')
    args = parser.parse_args()
    work = args.work.resolve()
    archive = ROOT / 'dist/pes13-fextendo-v3.4-cpu-balance-v2.zip'
    folder = archive.with_suffix('')
    if not args.validate_only and (archive.exists() or folder.exists()):
        raise FileExistsError('Existing artifact protected')
    files, manifest = collect(work, args.lsfg_prefix.resolve())
    if args.validate_only:
        print(json.dumps({'passed': True, 'validate_only': True, 'files': len(files),
                          'checks': manifest['checks'], 'nro_sha256': manifest['nro_sha256'],
                          'fex_sha256': manifest['fex_sha256']}, indent=2))
        return
    files['manifest.json'] = enc(manifest)
    for name, data in files.items():
        safe_name(name)
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 29, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            output.writestr(info, data)
    verified_zip(archive, sha(archive.read_bytes()))
    report = {'passed': True, 'path': str(archive), 'bytes': archive.stat().st_size,
              'sha256': sha(archive.read_bytes()), 'checks': manifest['checks'],
              'active_files': manifest['active_files']}
    (work / 'package.json').write_bytes(enc(report))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
