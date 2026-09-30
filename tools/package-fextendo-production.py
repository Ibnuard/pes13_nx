"""Package the checked native-only production build with its sources/evidence."""
import argparse
import importlib.util
import json
from pathlib import Path
import zipfile

import fextendo_package as p

BASE_SHA = 'c59faa0efa687272747c05741487fe2fb13f64c155b4bfd06e121de347b59b67'
GUIDE = 'docs/FEXTENDO-PRODUCTION-NO-LOG.md'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=p.ROOT / 'local/fex3/production-no-log-v2')
    args = parser.parse_args()
    work = args.work.resolve()
    base, _ = p.verified_zip(p.ROOT / 'dist/pes13-fextendo-v3.6-port-cleanup-v1.zip', BASE_SHA)
    runtime = p.read(work / 'runtime/runtime-build.json')
    patches = p.read(work / 'runtime/wine-patches.json')
    old = json.loads(base['evidence/runtime/runtime-build.json'])
    previous = json.loads(base['evidence/runtime/wine-patches.json'])
    assert runtime['silent_production'] is True
    for key in ('native_dependencies', 'ntdll_sha256', 'wow64_sha256', 'guest_sha256', 'toolchain_path'):
        assert runtime[key] == old[key], key
    assert patches['pe-source'] == previous['pe-source']
    changed = p.delta(previous['native-source'], patches['native-source'])
    assert changed == ['dlls/ntdll/unix/debug.c', 'dlls/ntdll/unix/horizon.c', 'wine-nx-probe/source/runtime.c'], changed
    files = {name: data for name, data in base.items() if name.startswith(('source/', 'licenses/'))}
    files[p.NRO] = p.checked(work / 'runtime/payload/pes13-fex.nro', runtime['nro_sha256'])
    elf = work / 'runtime/reference/pes13-fex.elf'
    p.checked(elf, runtime['native_elf_sha256'])
    spec = importlib.util.spec_from_file_location('stable', p.ROOT / 'tools/package-fex3-stability.py')
    stable = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stable)
    stable.verify_executable(elf, files[p.NRO])
    metadata = p.inspect_nro(files[p.NRO], (p.ROOT / 'assets/fextendo-v3/nro-icon.jpg').read_bytes(),
                             expected_title='PES13 - FEXTendo', expected_version='0.3.7')
    assert metadata == runtime['metadata'] and metadata['author'] == 'AndroSwitch Project'
    sources = set()
    p.add_sources(files, sources, runtime['patch_sources'])
    p.add_sources(files, sources, runtime['adapter_sources'], 'src/fex/')
    for name in (GUIDE, 'docs/FEX-PORT-PROVENANCE.md', 'docs/FEXTENDO-V3.6-PORT-CLEANUP.md',
                 'tools/package-fextendo-production.py', 'tests/fextendo_silent.py',
                 'tests/fex_reservations.py', 'tests/fex_resume_binary.py', 'tests/fex_worker_cores.py',
                 'tests/fex_balance_stable.py', 'tests/fextendo_silent_maintenance.py',
                 'tests/fextendo_silent_startup.py'):
        files['source/' + name] = (p.ROOT / name).read_bytes()
    wine = Path(runtime['native_source']).parent.parent
    for kind in ('native-source', 'pe-source'):
        for name, digest in patches[kind].items():
            files['source/generated/wine/' + kind + '/' + name] = p.checked(wine / kind / name, digest)
    for name in ('runtime-build.json', 'wine-patches.json'):
        files['evidence/runtime/' + name] = (work / 'runtime' / name).read_bytes()
    for name in ('silent', 'resume', 'maintenance-regression', 'startup-regression'):
        report = p.read(work / (name + '.json'))
        assert report['passed'] is True and report['native_elf_sha256'] == runtime['native_elf_sha256'], name
        files['evidence/checks/' + name + '.json'] = p.enc(report)
    files['README.md'] = (p.ROOT / GUIDE).read_bytes()
    files['THIRD_PARTY.md'] = (p.ROOT / 'THIRD_PARTY.md').read_bytes()
    files['LICENSE'] = (p.ROOT / 'LICENSE').read_bytes()
    for name in files:
        p.safe_name(name)
    manifest = {'kind': 'fextendo-production-no-log-v2', 'version': '0.3.7',
                'hardware_tested': False, 'requires': 'working v3.6 fast-api runtime installation',
                'baseline_sha256': BASE_SHA, 'nro_sha256': runtime['nro_sha256'],
                'native_elf_sha256': runtime['native_elf_sha256'], 'native_changed': changed,
                'active_files': [p.NRO], 'files': {name: p.sha(data) for name, data in sorted(files.items())}}
    files['manifest.json'] = p.enc(manifest)
    archive = p.ROOT / 'dist/pes13-fextendo-production-no-log-v2.zip'
    folder = archive.with_suffix('')
    if archive.exists() or folder.exists():
        raise FileExistsError('Existing artifact protected')
    for name, data in files.items():
        dest = folder / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for name, data in sorted(files.items()):
            output.writestr(name, data)
    p.verified_zip(archive, p.sha(archive.read_bytes()))
    report = {'passed': True, 'path': str(archive), 'bytes': archive.stat().st_size,
              'sha256': p.sha(archive.read_bytes()), 'nro_sha256': runtime['nro_sha256'],
              'checks': ['silent', 'resume', 'maintenance-regression', 'startup-regression']}
    (work / 'package.json').write_bytes(p.enc(report))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
