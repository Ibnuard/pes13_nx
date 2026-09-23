"""Package PERF31, its same-NRO policy control and a timing-disabled overlay."""
from pathlib import Path
import hashlib, importlib.util, io, json, zipfile
from nro_assets import inspect_nro

p = Path(__file__).resolve().parents[1]
w = p / 'local/perf31'
prefix = 'switch/pes13-nx/'
sha = lambda data: hashlib.sha256(data).hexdigest()


def package(variant, payload, metadata):
    files = dict(payload)
    for name in ('PERF31.md', 'PERF30-RESULT.md'):
        files[name] = (p / 'docs' / name).read_bytes()
    if any(n.endswith('.nro') for n in payload):
        files['THIRD_PARTY.md'] = (p / 'THIRD_PARTY.md').read_bytes()
        files['LICENSE'] = (p / 'LICENSE').read_bytes()
        files.update({f.relative_to(p).as_posix(): f.read_bytes()
                      for f in (p / 'licenses').rglob('*') if f.is_file()})
    manifest = dict(metadata, variant=variant, abi=4, hardware_tested=False,
                    cpu_sampling=False, scoped_worker_bigblock=0,
                    requires='Existing PES13 installation; overlays require PERF31 NRO',
                    files={name: sha(data) for name, data in files.items()})
    files['PERF31-manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            assert not name.startswith('/') and '..' not in Path(name).parts
            entry = zipfile.ZipInfo(name, (2026, 9, 22, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(entry, data)
    raw = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert z.testzip() is None and len(z.namelist()) == len(files)
        assert all(z.read(name) == data for name, data in files.items())
    target = p / 'dist' / f'pes13-perf31-{variant}.zip'
    if target.exists():
        assert target.read_bytes() == raw, f'Refusing to overwrite different package: {target}'
    else:
        with target.open('xb') as f:
            f.write(raw)
    return dict(path=str(target), variant=variant, bytes=len(raw), sha256=sha(raw),
                zip_integrity=True, hardware_tested=False)


def main():
    status = json.loads((w / 'build-status.json').read_text())
    assert status['state'] == 'complete' and status['restored']
    build = json.loads((w / 'build.json').read_text())
    verified = json.loads((w / 'verification.json').read_text())
    for key in ('source_restored', 'vendor_clean_at_pinned_revision',
                'same_math_and_copy_emitters_as_perf28', 'retained_cpu_policy',
                'native_submit_api_link_verified', 'horizon_selected_object_verified',
                'all_archive_copies_verified', 'zero_timeout_error_scan_experiment'):
        assert verified[key], key
    for name, digest in verified['changed_sources_sha256'].items():
        assert sha((p / name).read_bytes()) == digest, name
    nro = (w / 'payload' / prefix / 'pes13-nx.nro').read_bytes()
    assert sha(nro) == build['nro_sha256']
    meta = inspect_nro(nro, (p / 'assets/icon.jpg').read_bytes(), expected_title='PES13-NX PERF31')
    assert b'pes13-nx-0.2.0-perf31-fence-poll' in nro
    spec = importlib.util.spec_from_file_location('recovery', p / 'tools/package-perf29-recovery.py')
    recovery = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recovery)
    original = recovery.load_pinned(p / 'dist/pes13-perf29-worker-blocks.zip',
        'aaff5c547d7b631a3a8715654b5c810628620872ee8afd2766a847195a8140e0')
    control = recovery.load_pinned(p / 'dist/pes13-perf29-control.zip',
        'd2e6b746449de27e7e21afed1e667e1d0b6e6119e55c40cf5449ea373bcb49eb')
    baseline = recovery.control_files(original, control)
    cfg = prefix + 'drive_c/PES13/pes2013.wine-nx.txt'
    profile = prefix + 'profile.txt'
    growth = prefix + 'perf29-worker-blocks.txt'
    diagnostic = prefix + 'perf31-submit-diagnostics.txt'
    poll = prefix + 'perf31-fence-poll.txt'
    main_files = dict(baseline)
    main_files[prefix + 'pes13-nx.nro'] = nro
    main_files[diagnostic] = main_files[poll] = b'1\n'
    settings = {cfg: baseline[cfg], profile: b'0\n', growth: b'0\n',
                diagnostic: b'1\n', poll: b'0\n'}
    quiet = dict(settings, **{diagnostic: b'0\n', poll: b'1\n'})
    assert [n for n in baseline if baseline[n] != main_files[n]] == [prefix + 'pes13-nx.nro']
    assert set(main_files) - set(baseline) == {diagnostic, poll}
    assert [n for n in settings if settings[n] != main_files[n]] == [poll]
    assert [n for n in quiet if quiet[n] != main_files[n]] == [diagnostic]
    for data, count in ((main_files, 1), (settings, 0), (quiet, 0)):
        assert sum(n.endswith('.nro') for n in data) == count
        assert data[profile] == data[growth] == b'0\n'
        assert data[cfg].count(b'profile=0') == 1 and b'profile=1' not in data[cfg]
        assert not any(n.lower().endswith(('.exe', '.dat', '.reg', '.log', 'ntdll.dll')) for n in data)
        assert all('/users/' not in n for n in data)
    # The old ZIP was removed, but its original NRO survives in the build cache.
    # Restore the flags declared by package-perf25.py; later package recipes
    # carried its other runtime files forward unchanged. This is a new ZIP,
    # not a claim that the missing original ZIP has been recovered byte-for-byte.
    old_nro = (p / 'local/perf25/payload' / prefix / 'pes13-nx.nro').read_bytes()
    old_hash = '888c77730685a8cff44edf2f07d3146352dbd29b986413a7b2697b20ce9d2d81'
    assert sha(old_nro) == old_hash == json.loads((p / 'local/perf25/build.json').read_text())['nro_sha256']
    old_meta = inspect_nro(old_nro, (p / 'assets/icon.jpg').read_bytes(), expected_title='PES13-NX PERF25')
    assert b'pes13-nx-0.2.0-perf25-paircopy' in old_nro
    old_files = {n: data for n, data in baseline.items()
                 if n not in {growth, prefix + 'perf26-callret.txt', prefix + 'perf27-targeted-wake.txt'}}
    old_files[prefix + 'pes13-nx.nro'] = old_nro
    expected_flags = {'profile': 0, 'production': 1, 'no-balance': 0, 'perf23-balance': 1,
        'perf22-floatmath': 0, 'perf21-fastmath': 1, 'perf20-fusion': 1, 'perf19-matrix': 1,
        'perf17-hotblocks': 0, 'perf17-capture': 1, 'perf18-roundguard': 0,
        'perf8-turbo': 0, 'perf25-paircopy': 1}
    assert {n for n in old_files if n.endswith('.txt') and '/drive_c/' not in n} == {
        prefix + n + '.txt' for n in expected_flags}
    for name, value in expected_flags.items():
        assert old_files[prefix + name + '.txt'] == (str(value) + '\n').encode()
    assert sha(old_files[prefix + 'drive_c/windows/system32/winebox64.dll']) == '42463d635af0874c301317c481eeb401d42963ef4d119059b3e309bb14f7a46b'
    assert set(old_files) == {prefix + n + '.txt' for n in expected_flags} | {
        prefix + 'pes13-nx.nro', prefix + 'drive_c/PES13/pes2013.box64.txt', cfg,
        prefix + 'drive_c/windows/system32/winebox64.dll', prefix + 'drive_c/PES13/d3d9.dll'}
    reports = [
        package('fence-poll', main_files, dict(nro_metadata=meta, nro_sha256=sha(nro),
            error_scan_policy=True, submit_diagnostics=True, runtime_rebuilt=True)),
        package('control', settings, dict(same_nro=True, single_flag_control=True,
            error_scan_policy=False, submit_diagnostics=True, runtime_rebuilt=False)),
        package('quiet', quiet, dict(same_nro=True, single_flag_control=True,
            error_scan_policy=True, submit_diagnostics=False, runtime_rebuilt=False)),
        package('reference-perf25', old_files, dict(nro_metadata=old_meta, nro_sha256=old_hash,
            reference_runtime='PERF25', original_nro_verified=True, runtime_rebuilt=False,
            historical_flags_restored=True, old_zip_reconstructed_exactly=False)),
    ]
    (w / 'packages.json').write_text(json.dumps(reports, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(reports, indent=2))


if __name__ == '__main__':
    main()
