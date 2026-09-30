"""Package the verified production-v1 NRO rebuild and original pre-DFE DLL."""
import importlib.util
import json
from pathlib import Path
import zipfile

import fextendo_package as p

NAME = 'pes13-fextendo-production-v1-launchfix-dfe-rollback'
CHECKS = ('baseline-regression', 'binary-equivalence', 'startup-regression', 'silent', 'resume', 'maintenance-regression')
ROLLBACK_SHA = '17dcf3e78371a717a9c41da5bffa4d6a5755d6479afa0a8ade12abcc7639ad23'
GUIDE = 'docs/FEXTENDO-PRODUCTION-V1-LAUNCHFIX.md'


def main():
    work = p.ROOT / 'local/fex3/production-v1-launchfix'
    project = work / 'project'
    runtime = p.read(work / 'runtime/runtime-build.json')
    baseline = p.read(work / 'baseline-regression.json')
    assert baseline['generated_code_delta'] == {'native-source': ['dlls/ntdll/unix/debug.c'], 'pe-source': []}
    assert baseline['adapters_identical_to_production_v1']
    rollback, old = p.verified_zip(p.ROOT / 'dist/pes13-fextendo-v3.6-decode-worklists-v1.zip',
                                  '5b70b8357deb81aec583f7a49a9f4ac1f733822f50725f2449ed1ad9bf37268b')
    assert p.sha(rollback[p.FEX]) == old['fex_sha256'] == ROLLBACK_SHA
    assert b'[FEX3-DFE]' not in rollback[p.FEX]
    assert b'[FEX3-DECODE] v1' in rollback[p.FEX]
    # Verify the live integration and restored generated patch set too.
    previous_module = json.loads(rollback['evidence/module/build.json'])
    for name, digest in previous_module['adapter_sources'].items():
        p.checked(p.ROOT / name, digest)
    assert p.read(p.ROOT / 'local/fex3/dfe-revert/module/patches.json') == json.loads(rollback['evidence/module/patches.json'])

    files = {p.NRO: p.checked(work / 'runtime/payload/pes13-fex.nro', runtime['nro_sha256']),
             p.FEX: rollback[p.FEX]}
    elf = work / 'runtime/reference/pes13-fex.elf'
    p.checked(elf, runtime['native_elf_sha256'])
    spec = importlib.util.spec_from_file_location('stable', p.ROOT / 'tools/package-fex3-stability.py')
    stable = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stable)
    stable.verify_executable(elf, files[p.NRO])
    assert p.inspect_nro(files[p.NRO], (project / 'assets/fextendo-v3/nro-icon.jpg').read_bytes(),
                         expected_title='PES13 - FEXTendo', expected_version='0.3.7') == runtime['metadata']
    for path in sorted(project.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts:
            files['source/' + path.relative_to(project).as_posix()] = path.read_bytes()
    for name, data in rollback.items():
        if name.startswith('licenses/'):
            files[name] = data
        elif name.startswith('source/'):
            files['source/rollback-fex/' + name.removeprefix('source/')] = data
        elif name.startswith('evidence/'):
            files['evidence/rollback-fex/' + name.removeprefix('evidence/')] = data
    for name in CHECKS:
        report = p.read(work / (name + '.json'))
        assert report['passed'] is True and report['native_elf_sha256'] == runtime['native_elf_sha256'], name
        files['evidence/checks/' + name + '.json'] = p.enc(report)
    for name in ('runtime-build.json', 'wine-patches.json'):
        files['evidence/runtime/' + name] = (work / 'runtime' / name).read_bytes()
    for name in ('production-v1-launchfix.patch', 'generated-startup-fix.patch', 'build-command.json'):
        files['evidence/' + name] = (work / name).read_bytes()
    for name in (GUIDE, 'tools/build-fextendo-production-v1-launchfix.py',
                 'tools/package-fextendo-production-v1-launchfix.py',
                 'tests/fextendo_silent_startup.py', 'tests/fextendo_silent.py',
                 'tests/fextendo_silent_maintenance.py', 'tests/fex_reservations.py',
                 'tests/fex_resume_binary.py', 'tests/fex_worker_cores.py', 'tests/fex_balance_stable.py'):
        files['source/launchfix/' + name] = (p.ROOT / name).read_bytes()
    files['README.md'] = (p.ROOT / GUIDE).read_bytes()
    for name in ('LICENSE', 'THIRD_PARTY.md'):
        files[name] = rollback[name]
    for name in files:
        p.safe_name(name)
    manifest = {'kind': NAME, 'hardware_tested': False,
                'baseline_production_archive_sha256': baseline['baseline_archive_sha256'],
                'nro_sha256': runtime['nro_sha256'], 'fex_sha256': ROLLBACK_SHA,
                'native_elf_sha256': runtime['native_elf_sha256'],
                'active_files': [p.NRO, p.FEX], 'checks': list(CHECKS),
                'files': {name: p.sha(data) for name, data in sorted(files.items())}}
    files['manifest.json'] = p.enc(manifest)
    archive = p.ROOT / 'dist' / (NAME + '.zip')
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
    report = {'passed': True, 'path': str(archive), 'sha256': p.sha(archive.read_bytes()),
              'nro_sha256': runtime['nro_sha256'], 'fex_sha256': ROLLBACK_SHA,
              'active_files': [p.NRO, p.FEX], 'checks': list(CHECKS)}
    (work / 'package.json').write_bytes(p.enc(report))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
