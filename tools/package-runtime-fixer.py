"""Package the source-bound Runtime Fixer NRO as a copy-ready directory."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from nro_assets import inspect_nro

ROOT = Path(__file__).resolve().parents[1]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def package(work, native, output):
    output.resolve().relative_to((ROOT / 'dist').resolve())
    if output.resolve() == (ROOT / 'dist').resolve() or output.exists():
        raise ValueError('Use a new dist subdirectory')
    report = json.loads((work / 'build-report.json').read_text())
    baseline = json.loads((ROOT / 'local/production-va-recovery/build-report.json').read_text())
    assert report['passed'] and report['runtime_fixer'] == 1
    assert report['nro_sha256'] == sha(work / 'pes13-fex.nro')
    assert report['native_elf_sha256'] == sha(work / 'production.elf')
    assert report['diagnostic_file_writes'] == 'debug-launch-only'
    assert report['debug_console_scope'] == 'launcher-startup-only'
    assert report['launch_memory_gate_version'] == 3
    for key in ('native_fex_sources', 'rust_heap_binding', 'mesa_heap_binding'):
        assert report[key] == baseline[key], key
    for name, digest in baseline['native_dependencies'].items():
        assert report['native_dependencies'][name] == digest, name
    assert set(report['native_dependencies']) - set(baseline['native_dependencies']) == {'sdk/portlibs/switch/lib/libcurl.a'}
    sources = set()
    for group in ('feature_sources', 'build_scripts'):
        for name, digest in report[group].items():
            assert sha(ROOT / name) == digest, name
            sources.add(name)
    for name, digest in report['generated_sources'].items():
        assert sha(native / 'native-source' / name) == digest, name
    for name, digest in report['native_fex_sources'].items():
        assert sha(native / 'feature/src/fex' / name) == digest, name
    for name in ('production-arm64', 'startup-arm64', 'gamepad-arm64', 'keyboard-arm64', 'osk-arm64'):
        receipt = json.loads((work / 'tests' / (name + '.json')).read_text())
        assert receipt['passed'] and receipt['native_elf_sha256'] == report['native_elf_sha256'], name
    host = json.loads((work / 'tests/fixer-host.txt').read_text())
    assert host['passed'] and host['recovery_interruptions'] > 0
    assert 'PASS: HTTPS download' in (work / 'tests/download.txt').read_text()
    ui = json.loads((work / 'tests/ui.json').read_text());assert ui['passed']
    for name, digest in ui['sources'].items():
        assert sha(ROOT / name) == digest, name
        sources.add(name)
    metadata = inspect_nro((work / 'pes13-fex.nro').read_bytes(),
                           expected_title='PES13 - FEXTendo', expected_version='0.3.9-fixer1')

    def copy(src, relative):
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)

    copy(work / 'pes13-fex.nro', 'switch/pes13-fex/pes13-fex.nro')
    copy(work / 'build-report.json', 'evidence/build-report.json')
    for p in (work / 'tests').glob('*'):
        if p.is_file():copy(p, 'evidence/' + p.name)
    for p in (ROOT / 'licenses').glob('*'):
        if p.is_file():copy(p, 'licenses/' + p.name)
    for n in ('THIRD_PARTY.md', 'LICENSE', 'docs/RUNTIME-FIXER.md'):
        copy(ROOT / n, n)
    sources.update(['tools/runtime_fixer_catalog.py', 'tools/package-runtime-fixer.py',
                    'tests/fextendo_runtime_fixer_host.py', 'tests/fextendo_runtime_fixer_driver.c',
                    'tests/fextendo_runtime_download.c'])
    for n in sorted(sources):copy(ROOT / n, 'source/' + n)
    for n in report['generated_sources']:copy(native / 'native-source' / n, 'source/generated/' + n)
    (output / 'README.txt').write_text(
        'FEXTendo 0.3.9-fixer1 / Runtime Fixer preview\n\n'
        'Close PES13, then copy switch/ onto the SD root, replacing only pes13-fex.nro.\n'
        'Keep your existing complete r6 runtime and launch via the FEXTendo NSP.\n'
        'Settings > Maintenance > Check runtime verifies files offline.\n'
        'Repair runtime downloads the pinned official v0.3.8-r9 package if required.\n'
        'Use Wi-Fi and allow 300 MB of free SD space. Do not close during installation.\n'
        'Game files, patch DLLs, saves, registry and preferences are preserved.\n'
        'Only Wine/FEX/fonts/NLS and bundled renderer files are eligible.\n'
        'Normal launch remains without diagnostic logs; Debug launch enables them.\n'
        'Keep .runtime-fixer if an interrupted repair cannot recover.\n\n'
        'Build, host fault/recovery tests, UI and ARM64 checks passed.\n'
        'Switch Wi-Fi/TLS, SD installation and game launch after repair still need device testing.\n'
        'The previous r6 NRO remains in the v0.3.8-r9 GitHub release for rollback.\n', encoding='utf-8')
    manifest = {'passed': True, 'hardware_tested': False, 'version': '0.3.9-fixer1',
                'nro_sha256': report['nro_sha256'], 'native_elf_sha256': report['native_elf_sha256'],
                'metadata': metadata, 'runtime_release': 'v0.3.8-r9',
                'same_fex_sources': True, 'same_existing_native_dependencies': True,
                'files': {p.relative_to(output).as_posix(): sha(p) for p in output.rglob('*') if p.is_file()}}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    for n, digest in manifest['files'].items():assert sha(output / n) == digest, n
    print(json.dumps({'directory': str(output), 'nro_sha256': report['nro_sha256'], 'verified_files': len(manifest['files'])}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('build', 'native', 'output'):p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args();package(a.build, a.native, a.output)
