"""Package the checked decoder-only FEX candidate with its exact v3.6 rollback."""
import argparse
import json
from pathlib import Path
import zipfile
import fextendo_package as p

BASE = 'pes13-fextendo-v3.6-port-cleanup-v1.zip'
BASE_SHA = 'c59faa0efa687272747c05741487fe2fb13f64c155b4bfd06e121de347b59b67'
CHECKS = ('decode-worklists', 'fast-native', 'dispatch-cache', 'lookup-hash',
          'jit-metadata', 'smc', 'jit-metrics-binary')
GUIDE = 'docs/FEXTENDO-DECODE-WORKLISTS.md'


def collect(work):
    baseline, base = p.verified_zip(p.ROOT / 'dist' / BASE, BASE_SHA)
    build = p.read(work / 'module/build.json')
    patches = p.read(work / 'module/patches.json')
    old_build = json.loads(baseline['evidence/module/build.json'])
    old_patches = json.loads(baseline['evidence/module/patches.json'])
    if (build['fex_commit'] != old_build['fex_commit'] or
            build['toolchain_path'] != old_build['toolchain_path']):
        raise ValueError('Changed upstream/toolchain')
    if p.delta(old_build['adapter_sources'], build['adapter_sources']) != sorted([
            'src/fex/horizon_decode_set.h', 'src/fex/module_profile.cpp',
            'tools/fex_horizon_patches.py', 'tools/fex_decode_worklist_patches.py']):
        raise ValueError('Unexpected adapter delta')
    before = {r['path']: r['patched_sha256'] for r in old_patches['files']}
    after = {r['path']: r['patched_sha256'] for r in patches['files']}
    if p.delta(before, after) != ['FEXCore/Source/Interface/Core/Frontend.cpp',
                                'FEXCore/Source/Interface/Core/Frontend.h']:
        raise ValueError('Unexpected FEX code delta')
    rollback = p.checked(p.ROOT / 'local/fex3/port-cleanup-v1/module/libwow64fex.dll', old_build['sha256'])
    if old_build['sha256'] != base['unchanged_fex_sha256']:
        raise ValueError('Wrong rollback')
    candidate = p.checked(work / 'module/libwow64fex.dll', build['sha256'])
    if b'[FEX3-DECODE] v1' not in candidate or candidate == rollback:
        raise ValueError('Missing candidate marker/change')
    files = {p.FEX: candidate, 'rollback/' + p.FEX: rollback,
             'README.md': (p.ROOT / GUIDE).read_bytes()}
    files.update({name: data for name, data in baseline.items() if name.startswith('licenses/')})
    sources = set()
    p.add_sources(files, sources, build['adapter_sources'])
    for check in CHECKS:
        report = p.read(work / (check + '.json'))
        if report.get('passed') is not True or report.get('dll_sha256') != build['sha256']:
            raise ValueError('Wrong/failed binary check: ' + check)
        if 'native_elf_sha256' in report and report['native_elf_sha256'] != base['native_elf_sha256']:
            raise ValueError('Check used wrong unchanged native runtime: ' + check)
        if 'patches_sha256' in report and report['patches_sha256'] != p.sha((work / 'module/patches.json').read_bytes()):
            raise ValueError('Stale generated source receipt: ' + check)
        p.add_sources(files, sources, report.get('source_hashes', {}))
        p.add_sources(files, sources, report.get('test_sources', {}), 'tests/')
        files['evidence/checks/' + check + '.json'] = p.enc(report)
    source = Path(build['dll']).parents[2] / 'source-horizon'
    for name, digest in after.items():
        p.safe_name(name)
        files['source/generated/fex/' + name] = p.checked(source / name, digest)
    for name in ('build.json', 'patches.json'):
        files['evidence/module/' + name] = (work / 'module' / name).read_bytes()
    for name in ('LICENSE', 'THIRD_PARTY.md'):
        files[name] = (p.ROOT / name).read_bytes()
    sources.update((GUIDE, 'docs/FEX-PORT-PROVENANCE.md', 'tools/build-fex-module.py',
                    'tools/fex_toolchain.py', 'tools/package-fex3-decode-worklists.py',
                    'tools/fextendo_package.py', 'tools/nro_assets.py',
                    'tests/fex_smc.py', 'tests/fex_jit_latency_binary.py'))
    for name in sources:
        files['source/' + name] = (p.ROOT / name).read_bytes()
    # Also resolve the install guide's provenance link from the archive root.
    files['FEX-PORT-PROVENANCE.md'] = (p.ROOT / 'docs/FEX-PORT-PROVENANCE.md').read_bytes()
    for name in files:
        p.safe_name(name)
    if sorted(n for n in files if n.startswith('switch/')) != [p.FEX]:
        raise ValueError('Unexpected active payload')
    return files, {'kind': 'fextendo-v3.6-decode-worklists-v1', 'hardware_tested': False,
        'kickoff_fix_confirmed': False, 'requires': 'existing working FEXTendo v3.6 installation',
        'baseline_sha256': BASE_SHA, 'fex_sha256': build['sha256'],
        'rollback_fex_sha256': old_build['sha256'], 'native_runtime_unchanged': True,
        'checks': list(CHECKS), 'active_files': [p.FEX],
        'files': {name: p.sha(data) for name, data in sorted(files.items())}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=p.ROOT / 'local/fex3/decode-worklists-v1')
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    archive = p.ROOT / 'dist/pes13-fextendo-v3.6-decode-worklists-v1.zip'
    folder = archive.with_suffix('')
    if not args.validate_only and (archive.exists() or folder.exists()):
        raise FileExistsError('Existing artifact protected')
    files, manifest = collect(args.work.resolve())
    if args.validate_only:
        print(json.dumps({'passed': True, 'checks': list(CHECKS), 'active_files': manifest['active_files']}))
        return
    files['manifest.json'] = p.enc(manifest)
    for name, data in files.items():
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 30, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            output.writestr(info, data)
    checksum = p.sha(archive.read_bytes())
    p.verified_zip(archive, checksum)
    report = {'passed': True, 'path': str(archive), 'bytes': archive.stat().st_size,
              'sha256': checksum, 'checks': list(CHECKS), 'fex_sha256': manifest['fex_sha256']}
    (args.work / 'package.json').write_bytes(p.enc(report))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
