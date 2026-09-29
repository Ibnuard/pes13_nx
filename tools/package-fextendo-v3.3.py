"""Bind the two-renderer / JIT128 candidate to its actual binaries and checks."""
from pathlib import Path
import hashlib
import importlib.util
import json
import zipfile
from nro_assets import inspect_nro

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'local/fex3/renderer-jit-v1'
PREFIX = 'switch/pes13-fex/'
NRO = PREFIX + 'pes13-fex.nro'
FEX = PREFIX + 'drive_c/windows/system32/libwow64fex.dll'
CHECKS = ('launcher', 'cores', 'gap', 'balance', 'yield', 'resume', 'pipeline',
          'jit-log', 'unwind', 'memory', 'budget', 'short-trace', 'dxvk-core3')
PROFILES = {
    'dxvk-3.1.1': ('265888c31ca78dffa290c39cb7e50bfb02762590e41927906e46fb32f01497fa',
                   'config/fextendo/presets/dxvk.conf'),
    'dxvk-2.7.1-async': ('a2cd6841e102f37189527c118ec416fa5071ac4d3120762973d9a0c6c5fd067e',
                         'config/fextendo/gplasync-2.7.1.conf'),
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


def read(path):
    return json.loads(path.read_text())


def verified_zip(path, expected):
    checked(path, expected)
    with zipfile.ZipFile(path) as z:
        manifest = json.loads(z.read('manifest.json'))
        if z.testzip() or len(z.namelist()) != len(set(z.namelist())):
            raise ValueError('Invalid archive: ' + str(path))
        if set(z.namelist()) != set(manifest['files']) | {'manifest.json'}:
            raise ValueError('Inventory: ' + str(path))
        files = {name: z.read(name) for name in manifest['files']}
        for name, data in files.items():
            if sha(data) != manifest['files'][name]:
                raise ValueError('Member mismatch: ' + name)
        return files, manifest


def main():
    archive = ROOT / 'dist/pes13-fextendo-v3.3-renderers-jit128-v1.zip'
    folder = archive.with_suffix('')
    if archive.exists() or folder.exists():
        raise FileExistsError('Existing artifact protected')
    base, baseline = verified_zip(ROOT / 'dist/pes13-fextendo-dxvk-core3-v1.zip',
        '5d44615d0315a1dd8dd5562f13c42e695c82887c3717dd00001054c8ea2f4ea3')
    async_files, async_manifest = verified_zip(ROOT / 'dist/pes13-fextendo-dxvk-gplasync-2.7.1-v1.zip',
        'b2376da41e23cf1399da28b1e350b93f6c6d2d1a64377c095aab53c03b85dc6a')
    runtime = read(WORK / 'runtime/runtime-build.json')
    patches = read(WORK / 'runtime/wine-patches.json')
    module = read(WORK / 'module/build.json')
    old = json.loads(base['evidence/runtime/runtime-build.json'])
    for key in ('native_dependencies', 'ntdll_sha256', 'wow64_sha256', 'guest_sha256', 'toolchain_path'):
        if runtime[key] != old[key]:
            raise ValueError('Unexpected runtime dependency change: ' + key)
    for key, value in old.items():
        if isinstance(value, bool) and runtime.get(key) != value:
            raise ValueError('Unexpected build flag change: ' + key)
    old_module = json.loads(base['evidence/module/build.json'])
    adapter_delta = sorted(k for k in module['adapter_sources'].keys() | old_module['adapter_sources'].keys()
                           if module['adapter_sources'].get(k) != old_module['adapter_sources'].get(k))
    if adapter_delta != ['src/fex/module_profile.cpp', 'tools/fex_horizon_patches.py']:
        raise ValueError('Unexpected FEX adapter delta: ' + repr(adapter_delta))
    old_fex = {e['path']: e['patched_sha256'] for e in json.loads(base['evidence/module/patches.json'])['files']}
    new_fex = {e['path']: e['patched_sha256'] for e in read(WORK / 'module/patches.json')['files']}
    fex_delta = sorted(k for k in old_fex.keys() | new_fex.keys() if old_fex.get(k) != new_fex.get(k))
    if fex_delta != ['FEXCore/Source/Interface/Core/Core.cpp']:
        raise ValueError('Unexpected FEX core delta: ' + repr(fex_delta))
    previous = json.loads(base['evidence/runtime/wine-patches.json'])
    if patches['pe-source'] != previous['pe-source']:
        raise ValueError('Guest Wine changed')
    delta = sorted(name for name in patches['native-source'].keys() | previous['native-source'].keys()
                   if patches['native-source'].get(name) != previous['native-source'].get(name))
    if delta != ['wine-nx-probe/source/runtime.c']:
        raise ValueError('Unexpected native delta: ' + repr(delta))
    files = {name: data for name, data in base.items() if name.startswith('licenses/')}
    # Keep the upstream GPLAsync license, recipe and exact patches.
    for name, data in async_files.items():
        if name.startswith(('licenses/', 'upstream/')):
            if name in files and files[name] != data:
                raise ValueError('License/source collision: ' + name)
            files[name] = data
    files['evidence/baseline/core3-manifest.json'] = enc(baseline)
    files['evidence/baseline/gplasync-manifest.json'] = enc(async_manifest)
    files[NRO] = checked(WORK / 'runtime/payload/pes13-fex.nro', runtime['nro_sha256'])
    files[FEX] = checked(WORK / 'module/libwow64fex.dll', module['sha256'])
    elf = WORK / 'runtime/reference/pes13-fex.elf'
    checked(elf, runtime['native_elf_sha256'])
    metadata = inspect_nro(files[NRO], (ROOT / 'assets/fextendo-v3/nro-icon.jpg').read_bytes(),
                           expected_title='PES13 - FEXTendo', expected_version='0.3.4')
    if metadata != runtime['metadata'] or metadata['author'] != 'AndroSwitch Project':
        raise ValueError('NRO identity')
    spec = importlib.util.spec_from_file_location('stable', ROOT / 'tools/package-fex3-stability.py')
    stable = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stable)
    stable.verify_executable(elf, files[NRO])
    for marker in (b'pes13-fextendo-renderer-jit-v1', b'[FEXTENDO-RENDERER]', b'FEX_MAXINST=128\0',
                   b'FEX_MAXINST=500\0', b'FEX_MAXINST=5000\0'):
        if marker not in files[NRO]:
            raise ValueError('Missing NRO marker: ' + repr(marker))
    if b'maxinst=128 multiblock=1' not in files[FEX]:
        raise ValueError('FEX does not implement the candidate profile')
    # Bundle complete launcher artwork but no user-selected preferences.
    art = WORK / 'package/switch/pes13-fex/launcher'
    art_manifest = read(art / 'assets.json')
    for name, digest in art_manifest['files'].items():
        data = checked(art / name, digest)
        if Path(name).suffix in ('.rgba', '.bin', '.pcm'):
            files[PREFIX + 'launcher/' + name] = data
    files['evidence/launcher-assets.json'] = enc(art_manifest)
    for path in (ROOT / 'config/fextendo/presets').glob('*.dat'):
        files[PREFIX + 'launcher/presets/' + path.name] = path.read_bytes()
    for profile, (digest, config) in PROFILES.items():
        target = PREFIX + 'launcher/renderers/' + profile + '/'
        files[target + 'd3d9.dll'] = checked(art / 'renderers' / profile / 'd3d9.dll', digest)
        conf = (ROOT / config).read_bytes()
        if (art / 'renderers' / profile / 'dxvk.conf').read_bytes() != conf:
            raise ValueError('Tested profile config mismatch')
        files[target + 'dxvk.conf'] = conf
    files[PREFIX + 'fex_jit_small'] = b'1\n'
    files[PREFIX + 'fex_jit_large'] = b'0\n'
    for flag in ('fex_jit_small', 'fex_jit_large'):
        files['control-jit500/' + PREFIX + flag] = b'0\n'
        files['rollback/' + PREFIX + flag] = b'0\n'
    files['rollback/' + NRO] = base[NRO]
    files['rollback/' + FEX] = checked(ROOT / 'local/fex3/dxvk-core3/module/libwow64fex.dll',
        'a8fc15d13e9f0e6443ccffc8974018bf3167aa8e2844c76cb2fb78e3c1d28e92')
    for suffix in ('drive_c/PES13/d3d9.dll', 'drive_c/dxvk/d3d9.dll',
                   'drive_c/PES13/dxvk.conf', 'launcher/presets/dxvk.conf'):
        files['rollback/' + PREFIX + suffix] = async_files[PREFIX + suffix]
    sources = set()
    for mapping in (runtime['patch_sources'], {'src/fex/' + k: v for k, v in runtime['adapter_sources'].items()}, module['adapter_sources']):
        for name, digest in mapping.items():
            checked(ROOT / name, digest)
            sources.add(name)
    for name in CHECKS:
        path = WORK / (name + '.json')
        report = read(path)
        if report.get('passed') is not True or report['native_elf_sha256'] != runtime['native_elf_sha256']:
            raise ValueError('Stale/failed check: ' + name)
        if name == 'short-trace' and report['dll_sha256'] != module['sha256']:
            raise ValueError('Wrong trace module')
        if name == 'unwind' and report['fex_sha256'] != module['sha256']:
            raise ValueError('Wrong unwind module')
        for source, digest in report.get('source_hashes', report.get('source_sha256', {})).items():
            checked(ROOT / source, digest)
            sources.add(source)
        files['evidence/checks/' + name + '.json'] = path.read_bytes()
    jit = read(WORK / 'jit-metrics.json')
    if not jit['passed'] or jit['runtime_source_sha256'] != patches['native-source']['wine-nx-probe/source/runtime.c']:
        raise ValueError('JIT check mismatch')
    for name, digest in jit['sources'].items():
        checked(ROOT / 'src/fex' / name, digest)
        sources.add('src/fex/' + name)
    files['evidence/checks/jit-metrics.json'] = enc(jit)
    metadata_check = read(WORK / 'jit-metadata.json')
    if not metadata_check['passed'] or metadata_check['dll_sha256'] != module['sha256']:
        raise ValueError('Stale metadata optimization check')
    checked(WORK / 'module/patches.json', metadata_check['patches_sha256'])
    for name, digest in metadata_check['source_hashes'].items():
        checked(ROOT / name, digest)
        sources.add(name)
    files['evidence/checks/jit-metadata.json'] = enc(metadata_check)
    fex_source = Path(module['dll']).parents[2] / 'source-horizon'
    core_path = 'FEXCore/Source/Interface/Core/Core.cpp'
    files['source/generated/fex/' + core_path] = checked(fex_source / core_path, new_fex[core_path])
    for part, names in [('runtime', ('runtime-build.json', 'wine-patches.json')),
                        ('module', ('build.json', 'patches.json'))]:
        for name in names:
            files['evidence/' + part + '/' + name] = (WORK / part / name).read_bytes()
    files['source/generated/wine/wine-nx-probe/source/runtime.c'] = checked(
        Path(runtime['native_source']) / 'source/runtime.c', patches['native-source']['wine-nx-probe/source/runtime.c'])
    doc = 'docs/FEXTENDO-V3.3-RENDERERS-JIT.md'
    sources |= {doc, 'tools/package-fextendo-v3.3.py', 'tools/build-fex-module.py',
                'tests/fex_jit_latency.py', 'tests/run_fextendo_checks.py', 'tools/nro_assets.py',
                'tools/package-fex3-stability.py', 'config/fextendo/presets/dxvk.conf',
                'config/fextendo/gplasync-2.7.1.conf', 'assets/fextendo-v3/nro-icon.jpg'}
    for name in sources:
        files['source/' + name] = (ROOT / name).read_bytes()
    files['README.md'] = (ROOT / doc).read_bytes()
    files['THIRD_PARTY.md'] = (ROOT / 'THIRD_PARTY.md').read_bytes()
    active = sorted(name for name in files if name.startswith('switch/'))
    if any(name.endswith(('configuration.ini', 'settings.dat', 'renderer-choice.txt', 'selected.txt')) for name in active):
        raise ValueError('Package overwrites a user setting')
    manifest = {'kind': 'fextendo-v3.3-renderers-jit128-v1', 'hardware_tested': False,
        'stutter_fix_confirmed': False, 'version': '0.3.4', 'default_renderer': 'dxvk-3.1.1',
        'jit_candidate_maxinst': 128, 'jit_control_maxinst': 500,
        'requires': 'working FEXTendo core3 / GPLAsync trial installation; same Wine/Mesa dependencies',
        'nro_sha256': runtime['nro_sha256'], 'native_elf_sha256': runtime['native_elf_sha256'],
        'fex_sha256': module['sha256'], 'native_changed': delta,
        'fex_adapter_changed': adapter_delta, 'fex_core_changed': fex_delta,
        'checks': list(CHECKS) + ['jit-metrics', 'jit-metadata'], 'active_files': active,
        'files': {name: sha(data) for name, data in sorted(files.items())}}
    files['manifest.json'] = enc(manifest)
    for name, data in files.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 29, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)
    verified_zip(archive, sha(archive.read_bytes()))
    report = {'passed': True, 'path': str(archive), 'bytes': archive.stat().st_size,
              'sha256': sha(archive.read_bytes()), 'active_files': active}
    (WORK / 'package.json').write_bytes(enc(report))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
