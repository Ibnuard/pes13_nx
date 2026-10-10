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
    version = report.get('app_version', '0.3.9-fixer1')
    assert version in ('0.3.9-fixer1', '0.3.9-kit1', '0.3.9-kit2', '0.3.9-kit3', '0.3.9-kit4', '0.3.9-kit5', '0.3.9-kit7', '0.3.9-kit8', '0.3.9-kit9', '0.3.9-kit10', '0.3.9-kit11', '0.3.9-kit12', '0.3.9-kit13', '0.3.9-kit14', '0.3.9-kit15')
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
    if version in ('0.3.9-kit1', '0.3.9-kit2', '0.3.9-kit3', '0.3.9-kit4', '0.3.9-kit5', '0.3.9-kit7', '0.3.9-kit8', '0.3.9-kit9', '0.3.9-kit10', '0.3.9-kit11', '0.3.9-kit12', '0.3.9-kit13', '0.3.9-kit14', '0.3.9-kit15'):
        assert report['process_params_version'] == 1
        receipt = json.loads((work / 'tests/process-params-arm64.json').read_text())
        assert receipt['passed'] and receipt['native_elf_sha256'] == report['native_elf_sha256']
        reproduction = json.loads((work / 'tests/current-directory-x86.json').read_text())
        assert reproduction['passed'] and reproduction['guest_ntdll_sha256'] == receipt['guest_ntdll_sha256']
        sources.update(['tests/fextendo_current_directory.py', 'tests/fextendo_process_params_binary.py'])
    if version in ('0.3.9-kit2', '0.3.9-kit3', '0.3.9-kit4', '0.3.9-kit5', '0.3.9-kit7', '0.3.9-kit8', '0.3.9-kit9', '0.3.9-kit10', '0.3.9-kit11', '0.3.9-kit12', '0.3.9-kit13', '0.3.9-kit14', '0.3.9-kit15'):
        assert report['section_anchor_version'] == 1
        receipt = json.loads((work / 'tests/section-anchors-arm64.json').read_text())
        assert receipt['passed'] and receipt['native_elf_sha256'] == report['native_elf_sha256']
        host_anchors = json.loads((work / 'tests/section-anchors-host.json').read_text())
        assert host_anchors['passed']
        for name, digest in host_anchors['sources'].items():
            assert sha(ROOT / name) == digest, name
            sources.add(name)
        for name, digest in host_anchors['generated_sources'].items():
            assert report['generated_sources'][name] == digest, name
        sources.update(['tests/fextendo_section_anchors_binary.py', 'tests/fextendo_page_store_binary.py',
                        'tests/fex_reservations.py'])
    if version in ('0.3.9-kit3', '0.3.9-kit4', '0.3.9-kit5', '0.3.9-kit7', '0.3.9-kit8', '0.3.9-kit9', '0.3.9-kit10', '0.3.9-kit11', '0.3.9-kit12', '0.3.9-kit13', '0.3.9-kit14', '0.3.9-kit15'):
        assert report['vm_fault_trace_version'] == (1 if version == '0.3.9-kit3' else 2)
        receipt = json.loads((work / 'tests/vm-fault-arm64.json').read_text())
        assert receipt['passed'] and receipt['native_elf_sha256'] == report['native_elf_sha256']
        sources.add('tests/fextendo_vm_fault_binary.py')
    if report.get('fex_flag_control') or version in ('0.3.9-kit5', '0.3.9-kit7', '0.3.9-kit8', '0.3.9-kit9', '0.3.9-kit10', '0.3.9-kit11', '0.3.9-kit12', '0.3.9-kit13', '0.3.9-kit14', '0.3.9-kit15'):
        receipt = json.loads((work / 'tests/flag-control-arm64.json').read_text())
        assert receipt['passed'] and receipt['native_elf_sha256'] == report['native_elf_sha256']
        if version in ('0.3.9-kit5', '0.3.9-kit7', '0.3.9-kit8', '0.3.9-kit9', '0.3.9-kit10', '0.3.9-kit11', '0.3.9-kit12', '0.3.9-kit13', '0.3.9-kit14', '0.3.9-kit15'):
            assert not report['fex_flag_control'] and report['fex_optimizations'] == 'normal'
            assert receipt['expected_o0'] == '0'
        sources.add('tests/fextendo_flag_control.py')
    if version in ('0.3.9-kit5', '0.3.9-kit7', '0.3.9-kit8', '0.3.9-kit9', '0.3.9-kit10', '0.3.9-kit11', '0.3.9-kit12', '0.3.9-kit13', '0.3.9-kit14', '0.3.9-kit15'):
        assert report['vm_protect_trace_version'] == 1
        receipt = json.loads((work / 'tests/protect-trace-host.json').read_text())
        assert receipt['passed']
        assert receipt['virtual_source_sha256'] == report['generated_sources']['dlls/ntdll/unix/virtual.c']
        sources.add('tests/fextendo_protect_trace_host.py')
    if version in ('0.3.9-kit7', '0.3.9-kit8', '0.3.9-kit9', '0.3.9-kit10', '0.3.9-kit11', '0.3.9-kit12', '0.3.9-kit13', '0.3.9-kit14', '0.3.9-kit15'):
        assert report['directory_cursor_version'] == 2
        receipt = json.loads((work / 'tests/directory-host.json').read_text())
        assert receipt['passed'] and receipt['horizon_sha256'] == report['generated_sources']['dlls/ntdll/unix/horizon.c']
        for name, digest in receipt['sources'].items():
            assert sha(ROOT / name) == digest, name
            sources.add(name)
    host = json.loads((work / 'tests/fixer-host.txt').read_text())
    if version in ('0.3.9-kit8', '0.3.9-kit9', '0.3.9-kit10', '0.3.9-kit11', '0.3.9-kit12', '0.3.9-kit13', '0.3.9-kit14', '0.3.9-kit15'):
        assert report['directory_metadata_version'] == (2 if version in ('0.3.9-kit9','0.3.9-kit10', '0.3.9-kit11', '0.3.9-kit12', '0.3.9-kit13', '0.3.9-kit14', '0.3.9-kit15') else 1)
        receipt = json.loads((work / 'tests/directory-meta-host.json').read_text())
        assert receipt['passed'] and receipt['real_timestamps'] and receipt['quiet_observer']
        for name, digest in receipt['generated'].items():
            assert report['generated_sources']['dlls/ntdll/unix/' + name] == digest, name
        for name, digest in receipt['sources'].items():
            assert sha(ROOT / name) == digest, name
            sources.add(name)
    assert host['passed'] and host['recovery_interruptions'] > 0
    if version in ('0.3.9-kit9','0.3.9-kit10', '0.3.9-kit11', '0.3.9-kit12', '0.3.9-kit13', '0.3.9-kit14', '0.3.9-kit15'):
        receipt = json.loads((work / 'tests/asset-scan-arm64.json').read_text())
        assert receipt['passed'] and receipt['native_elf_sha256'] == report['native_elf_sha256']
        for name, digest in receipt['sources'].items():
            assert sha(ROOT / name) == digest, name
            sources.add(name)
        audit = json.loads((work / 'tests/afs2fs-consumer.json').read_text())
        assert audit['passed'] and not audit['file_modified']
        assert audit['dll_sha256'] == 'd5f6cfa5438978c0ba57310fff67e1a7a8d167beffc93bee3cc6cc8dd4560c26'
        assert {a['find_data_offset'] for a in audit['direct_accesses']} == {0, 44}
        sources.add('tests/kitserver_finddata_audit.py')
        meta = json.loads((work / 'tests/directory-meta-host.json').read_text())
        assert meta['asset_entries_without_timestamp_ipc'] == 14258 and meta['policy_override']
    if version in ('0.3.9-kit10', '0.3.9-kit11', '0.3.9-kit12', '0.3.9-kit13', '0.3.9-kit14', '0.3.9-kit15'):
        assert report['wait_probe_version'] == (2 if version in ('0.3.9-kit11', '0.3.9-kit12', '0.3.9-kit13', '0.3.9-kit14', '0.3.9-kit15') else 1)
        for name in ('wait-host', 'wait-arm64'):
            receipt = json.loads((work / 'tests' / (name + '.json')).read_text())
            assert receipt['passed']
            if name == 'wait-arm64':assert receipt['native_elf_sha256'] == report['native_elf_sha256']
            for source, digest in receipt['sources'].items():
                assert sha(ROOT / source) == digest, source
                sources.add(source)
    if version in ('0.3.9-kit11', '0.3.9-kit12', '0.3.9-kit13', '0.3.9-kit14', '0.3.9-kit15'):
        assert report['guest_va_partition_version'] == 1
        for name in ('guest-va-host', 'guest-va-arm64', 'reservations-arm64'):
            receipt = json.loads((work / 'tests' / (name + '.json')).read_text())
            assert receipt['passed']
            if name != 'guest-va-host':assert receipt['native_elf_sha256'] == report['native_elf_sha256']
            for source, digest in receipt.get('sources', {}).items():
                assert sha(ROOT / source) == digest, source
                sources.add(source)
    if version in ('0.3.9-kit12', '0.3.9-kit13', '0.3.9-kit14', '0.3.9-kit15'):
        assert report['anonymous_pipe_version'] == (3 if version in ('0.3.9-kit14', '0.3.9-kit15') else 2 if version == '0.3.9-kit13' else 1)
        for name in ('anon-pipe-host','anon-pipe-arm64'):
            receipt=json.loads((work/'tests'/(name+'.json')).read_text())
            assert receipt['passed']
            if name=='anon-pipe-host':
                assert receipt['horizon_source_sha256']==report['generated_sources']['dlls/ntdll/unix/horizon.c']
            else:assert receipt['native_elf_sha256']==report['native_elf_sha256']
            for source,digest in receipt['sources'].items():
                assert sha(ROOT/source)==digest,source
                sources.add(source)
    if version in ('0.3.9-kit13', '0.3.9-kit14', '0.3.9-kit15'):
        for name in ('pipe-quota-host','pipe-quota-arm64'):
            receipt=json.loads((work/'tests'/(name+'.json')).read_text())
            assert receipt['passed'] and len(receipt['checks']) == 2
            assert all(check['passed'] for check in receipt['checks'])
            assert receipt['checks'][0]['baseline'] and not receipt['checks'][1]['baseline']
            if name=='pipe-quota-arm64':assert receipt['native_elf_sha256']==report['native_elf_sha256']
            for source,digest in receipt['sources'].items():
                assert sha(ROOT/source)==digest,source
                sources.add(source)
    if version in ('0.3.9-kit14', '0.3.9-kit15'):
        for name in ('pipe-lifetime-host','pipe-lifetime-arm64'):
            receipt=json.loads((work/'tests'/(name+'.json')).read_text())
            assert receipt['passed'] and len(receipt['checks'])==2
            assert all(c['passed'] for c in receipt['checks'])
            assert receipt['checks'][0]['baseline'] and not receipt['checks'][1]['baseline']
            if name=='pipe-lifetime-arm64':assert receipt['native_elf_sha256']==report['native_elf_sha256']
            for source,digest in receipt['sources'].items():
                assert sha(ROOT/source)==digest,source
                sources.add(source)
    if version == '0.3.9-kit15':
        assert report['commit_recovery_version'] == 1
        for name in ('commit-arm64', 'memory-failure-arm64', 'pool-pressure-arm64'):
            receipt = json.loads((work / 'tests' / (name + '.json')).read_text())
            assert receipt['passed'] and receipt['native_elf_sha256'] == report['native_elf_sha256'], name
            for source, digest in receipt['sources'].items():
                assert sha(ROOT / source) == digest, source
                sources.add(source)
    assert 'PASS: HTTPS download' in (work / 'tests/download.txt').read_text()
    ui = json.loads((work / 'tests/ui.json').read_text());assert ui['passed']
    for name, digest in ui['sources'].items():
        assert sha(ROOT / name) == digest, name
        sources.add(name)
    metadata = inspect_nro((work / 'pes13-fex.nro').read_bytes(),
                           expected_title='PES13 - FEXTendo', expected_version=version)

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
        'FEXTendo '+version+' / Runtime Fixer + startup preview\n\n'
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
        'The previous r6 NRO remains in the v0.3.8-r9 GitHub release for rollback.\n'+
        ('\nKitserver startup fix: reserve MAX_PATH WCHARs for the mutable current directory.\n'
         'Previously SetCurrentDirectory overwrote the adjacent DLL search path.\n'
         'The shipped x86 Wine reproduces this corruption; the new ARM64 constructor\n'
         'and guest directory-change regression tests preserve the DLL path.\n'
         'No Wine DLL, FEX core, DXVK or Kitserver/game file is replaced by this overlay.\n'
         + ('Directory enumeration uses a persistent cursor with bounded trace.\n' if version in ('0.3.9-kit7', '0.3.9-kit8', '0.3.9-kit9', '0.3.9-kit10', '0.3.9-kit11', '0.3.9-kit12', '0.3.9-kit13', '0.3.9-kit14', '0.3.9-kit15') else 'Directory enumeration optimization is deferred.\n') +
         'Try Debug launch with the patch and retain fex-runtime.log. Look for [PROCESS-PATH] v1.\n'
         if version in ('0.3.9-kit1', '0.3.9-kit2', '0.3.9-kit3', '0.3.9-kit4', '0.3.9-kit5', '0.3.9-kit7', '0.3.9-kit8', '0.3.9-kit9', '0.3.9-kit10', '0.3.9-kit11', '0.3.9-kit12', '0.3.9-kit13', '0.3.9-kit14', '0.3.9-kit15') else '')+
        ('\nKit2 shared-section fix: split internal anchors after a clean free-address search miss.\n'
         'The guest view remains contiguous and aliases the same pages, without extra data copies.\n'
         'Metadata and kernel errors remain terminal; partial progress is cleaned up on failure.\n'
         'Host sanitizer tests and ARM64 old/new tests reproduce the 69.5-MiB failure and recover it.\n'
         'This needs sufficient total free address space and cannot solve true memory exhaustion.\n'
         'Debug evidence: [SECTION-ANCHOR] v1 recovered bytes=... pieces=... shared_pages=1.\n'
         'The startup version label now follows the actual NRO version.\n'
         if version in ('0.3.9-kit2', '0.3.9-kit3', '0.3.9-kit4', '0.3.9-kit5', '0.3.9-kit7', '0.3.9-kit8', '0.3.9-kit9', '0.3.9-kit10', '0.3.9-kit11', '0.3.9-kit12', '0.3.9-kit13', '0.3.9-kit14', '0.3.9-kit15') else '')+
        ('\nKit3 records logical Wine and native Horizon page permissions for unresolved\n'
         'memory faults in Debug launch only (up to 16 records). This observation\n'
         'does not change page protections or suppress errors; it is not a verified\n'
         'fix for the access violation seen after loading the updated ISN patch.\n'
         if version == '0.3.9-kit3' else '')+
        ('\nKit4 logs up to 32 distinct unresolved page/protection/kind events.\n'
         'Repeated native guard faults cannot consume the whole log budget.\n'
         'Reports include the faulting PC and Wine/Horizon permissions.\n'
         if version in ('0.3.9-kit4', '0.3.9-kit5', '0.3.9-kit7', '0.3.9-kit8', '0.3.9-kit9', '0.3.9-kit10', '0.3.9-kit11', '0.3.9-kit12', '0.3.9-kit13', '0.3.9-kit14', '0.3.9-kit15') else '')+
        ('\nKit5 restores normal FEX optimization (guest FEX_O0=0). Kit4 failed\n'
         'in ntdll before reaching the patch, so its O0 trial was inconclusive.\n'
         'Debug-only VM-PROTECT records show up to 64 main-image protection\n'
         'requests and their callers, results and native permissions.\n'
         'This improves diagnosis; patch launch compatibility still needs device testing.\n'
         if version in ('0.3.9-kit5', '0.3.9-kit7', '0.3.9-kit8', '0.3.9-kit9', '0.3.9-kit10', '0.3.9-kit11', '0.3.9-kit12', '0.3.9-kit13', '0.3.9-kit14', '0.3.9-kit15') else '')+
        ('\nSTARTUP COMPARISON: guest FEX_O0=1 disables flag and x87 IR optimization\n'
         'passes. This is NOT Box64 SAFEFLAGS and NOT a performance preset.\n'
         'A successful launch is not yet verified; use Debug launch and retain the log.\n'
         if report.get('fex_flag_control') else ''), encoding='utf-8')
    manifest = {'passed': True, 'hardware_tested': False, 'version': version,
                'nro_sha256': report['nro_sha256'], 'native_elf_sha256': report['native_elf_sha256'],
                'metadata': metadata, 'runtime_release': 'v0.3.8-r9',
                'fex_flag_control': report.get('fex_flag_control', 0),
                'same_fex_sources': True, 'same_existing_native_dependencies': True,
                'files': {p.relative_to(output).as_posix(): sha(p) for p in output.rglob('*') if p.is_file()}}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    for n, digest in manifest['files'].items():assert sha(output / n) == digest, n
    print(json.dumps({'directory': str(output), 'nro_sha256': report['nro_sha256'], 'verified_files': len(manifest['files'])}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('build', 'native', 'output'):p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args();package(a.build, a.native, a.output)
