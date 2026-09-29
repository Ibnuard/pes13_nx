"""Package the current v3.6 native-only cleanup against its checked baseline."""
from pathlib import Path
import argparse, importlib.util, json, re, zipfile
from urllib.parse import unquote
import fextendo_package as p

ROOT = p.ROOT
WORK = ROOT / 'local/fex3/port-cleanup-v1'
BASE = 'pes13-fextendo-v3.6-fast-api-v1.zip'
BASE_SHA = 'fe3011bd1bbddddc998e6128cf5ca0aa6be5cdcd1cb126807ed786a8539bbf16'
CHECKS = p.CHECKS + ('fast-api', 'hotspots', 'fast-native')
EXTRA = p.EXTRA_CHECKS
GUIDE = 'docs/FEXTENDO-V3.6-PORT-CLEANUP.md'


def collect(work):
    base, baseline = p.verified_zip(ROOT / 'dist' / BASE, BASE_SHA)
    runtime = p.read(work / 'runtime/runtime-build.json')
    patches = p.read(work / 'runtime/wine-patches.json')
    module = p.read(work / 'module/build.json')
    old = json.loads(base['evidence/runtime/runtime-build.json'])
    previous = json.loads(base['evidence/runtime/wine-patches.json'])
    for key in ('native_dependencies', 'ntdll_sha256', 'wow64_sha256', 'guest_sha256', 'toolchain_path'):
        if runtime[key] != old[key]:
            raise ValueError('Changed dependency: ' + key)
    # The retired backend is the only build feature removed from this baseline.
    for key, value in old.items():
        if isinstance(value, bool) and key != 'lsfg' and runtime.get(key) != value:
            raise ValueError('Changed runtime flag: ' + key)
    if runtime.get('lsfg') or 'lsfg_backend' in runtime:
        raise ValueError('Retired backend still linked')
    if patches['pe-source'] != previous['pe-source']:
        raise ValueError('Changed guest Wine')
    native_delta = p.delta(previous['native-source'], patches['native-source'])
    expected = ['dlls/win32u/vulkan.c', 'wine-nx-probe/CMakeLists.txt', 'wine-nx-probe/source/runtime.c']
    if native_delta != expected:
        raise ValueError('Unexpected native delta: ' + repr(native_delta))
    if p.checked(work / 'module/libwow64fex.dll', module['sha256']) != base[p.FEX]:
        raise ValueError('Changed FEX module')
    if (work / 'module/build.json').read_bytes() != base['evidence/module/build.json']:
        raise ValueError('Changed FEX build receipt')
    files = {p.NRO: p.checked(work / 'runtime/payload/pes13-fex.nro', runtime['nro_sha256'])}
    files.update({name: data for name, data in base.items()
                  if name.startswith('licenses/') and 'LSFG' not in name})
    elf = work / 'runtime/reference/pes13-fex.elf'
    elf_bytes = p.checked(elf, runtime['native_elf_sha256'])
    metadata = p.inspect_nro(files[p.NRO], (ROOT / 'assets/fextendo-v3/nro-icon.jpg').read_bytes(),
                             expected_title='PES13 - FEXTendo', expected_version='0.3.7')
    if metadata != runtime['metadata'] or metadata['author'] != 'AndroSwitch Project':
        raise ValueError('Wrong NRO identity')
    for marker in (b'wine_nx_lsfg', b'lsfgvk', b'WINE_NX_LSFG', b'[LSFG]', b'Lossless.dll', b'Frame generation'):
        if marker in elf_bytes or marker in files[p.NRO]:
            raise ValueError('Retired backend remains in binary: ' + repr(marker))
    spec = importlib.util.spec_from_file_location('stable', ROOT / 'tools/package-fex3-stability.py')
    stable = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stable)
    stable.verify_executable(elf, files[p.NRO])
    sources = set()
    for mapping in (runtime['patch_sources'], module['adapter_sources']):
        p.add_sources(files, sources, mapping)
    p.add_sources(files, sources, runtime['adapter_sources'], 'src/fex/')
    for name in CHECKS:
        report = p.read(work / (name + '.json'))
        if report.get('passed') is not True or report['native_elf_sha256'] != runtime['native_elf_sha256']:
            raise ValueError('Stale/failed runtime check: ' + name)
        if name in ('short-trace', 'hotspots', 'fast-native') and report['dll_sha256'] != module['sha256']:
            raise ValueError('Wrong tested FEX module: ' + name)
        if name == 'unwind' and report['fex_sha256'] != module['sha256']:
            raise ValueError('Wrong unwind FEX module')
        p.add_sources(files, sources, report.get('source_hashes', report.get('source_sha256', {})))
        files['evidence/checks/' + name + '.json'] = p.enc(report)
    jit = p.read(work / 'jit-metrics.json')
    if jit.get('passed') is not True or jit['runtime_source_sha256'] != patches['native-source']['wine-nx-probe/source/runtime.c']:
        raise ValueError('Stale JIT metrics check')
    p.add_sources(files, sources, jit['sources'], 'src/fex/')
    files['evidence/checks/jit-metrics.json'] = p.enc(jit)
    for name in ('jit-metadata', 'dispatch-cache', 'lookup-hash'):
        report = p.read(work / (name + '.json'))
        if report.get('passed') is not True or report['dll_sha256'] != module['sha256']:
            raise ValueError('Stale FEX check: ' + name)
        if name == 'jit-metadata':
            p.checked(work / 'module/patches.json', report['patches_sha256'])
            p.add_sources(files, sources, report['source_hashes'])
        else:
            p.add_sources(files, sources, report['test_sources'], 'tests/')
        files['evidence/checks/' + name + '.json'] = p.enc(report)
    wine = Path(runtime['native_source']).parent.parent
    for kind in ('native-source', 'pe-source'):
        for name, digest in patches[kind].items():
            p.safe_name(name)
            files['source/generated/wine/' + kind + '/' + name] = p.checked(wine / kind / name, digest)
    fex_source = Path(module['dll']).parents[2] / 'source-horizon'
    for item in p.read(work / 'module/patches.json')['files']:
        p.safe_name(item['path'])
        files['source/generated/fex/' + item['path']] = p.checked(fex_source / item['path'], item['patched_sha256'])
    for section, names in [('runtime', ('runtime-build.json', 'wine-patches.json')), ('module', ('build.json', 'patches.json'))]:
        for name in names:
            files['evidence/' + section + '/' + name] = (work / section / name).read_bytes()
    sources |= {'README.md', 'THIRD_PARTY.md', 'LICENSE', 'dependencies.json', GUIDE,
                'docs/FEX-PORT-PROVENANCE.md', 'src/fex/README.md',
                'tools/package-fextendo-v3.6.py', 'tools/fextendo_package.py', 'tools/nro_assets.py',
                'tools/package-fex3-stability.py', 'tools/build-fex-module.py', 'tests/run_fextendo_checks.py'}
    pending = [name for name in sources if name.endswith('.md')]
    visited = set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        for link in re.findall(r'\]\(([^)]+)\)', (ROOT / name).read_text()):
            if link.startswith(('https://', 'http://', '#')):
                continue
            target = ((ROOT / name).parent / unquote(link.split('#', 1)[0])).resolve()
            if target.is_file() and target.is_relative_to(ROOT):
                relative = target.relative_to(ROOT).as_posix()
                sources.add(relative)
                if relative.endswith('.md'):
                    pending.append(relative)
    for name in sources:
        files['source/' + name] = (ROOT / name).read_bytes()
    files['README.md'] = (ROOT / GUIDE).read_bytes()
    files['THIRD_PARTY.md'] = (ROOT / 'THIRD_PARTY.md').read_bytes()
    files['LICENSE'] = (ROOT / 'LICENSE').read_bytes()
    # Only ship the new executable. No old executable, DLL, saved setting or backend archive is inherited.
    if sorted(name for name in files if name.startswith('switch/')) != [p.NRO]:
        raise ValueError('Unexpected active payload')
    for name in files:
        p.safe_name(name)
        if any(part in name.lower() for part in ('lsfg', 'lossless', 'frame-generation')):
            raise ValueError('Retired payload included: ' + name)
    return files, {'kind': 'fextendo-v3.6-port-cleanup-v1', 'version': '0.3.7',
        'hardware_tested': False, 'stutter_fix_confirmed': False,
        'requires': 'working v3.6 fast-api-v1 installation; native executable update only',
        'baseline_sha256': BASE_SHA, 'nro_sha256': runtime['nro_sha256'],
        'native_elf_sha256': runtime['native_elf_sha256'], 'unchanged_fex_sha256': module['sha256'],
        'native_changed': native_delta, 'checks': list(CHECKS + EXTRA),
        'active_files': [p.NRO], 'files': {name: p.sha(data) for name, data in sorted(files.items())}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=WORK)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    archive = ROOT / 'dist/pes13-fextendo-v3.6-port-cleanup-v1.zip'
    folder = archive.with_suffix('')
    if not args.validate_only and (archive.exists() or folder.exists()):
        raise FileExistsError('Existing artifact protected')
    files, manifest = collect(args.work.resolve())
    if args.validate_only:
        print(json.dumps({'passed': True, 'files': len(files), 'checks': manifest['checks']}, indent=2))
        return
    files['manifest.json'] = p.enc(manifest)
    for name, data in files.items():
        dest = folder / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 29, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            output.writestr(info, data)
    p.verified_zip(archive, p.sha(archive.read_bytes()))
    report = {'passed': True, 'path': str(archive), 'bytes': archive.stat().st_size,
              'sha256': p.sha(archive.read_bytes()), 'checks': manifest['checks']}
    (args.work / 'package.json').write_bytes(p.enc(report))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
