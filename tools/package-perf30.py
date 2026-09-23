"""Package native diagnosis, a quiet overlay and exact PERF29 control rollback."""
from pathlib import Path
import hashlib, importlib.util, io, json, zipfile
from nro_assets import inspect_nro

p = Path(__file__).resolve().parents[1]
w = p / 'local/perf30'
prefix = 'switch/pes13-nx/'
sha = lambda data: hashlib.sha256(data).hexdigest()

def package(variant, payload, metadata):
    files = dict(payload)
    files['PERF30.md'] = (p / 'docs/PERF30.md').read_bytes()
    if variant != 'quiet':
        files['THIRD_PARTY.md'] = (p / 'THIRD_PARTY.md').read_bytes()
        files['LICENSE'] = (p / 'LICENSE').read_bytes()
        files.update({f.relative_to(p).as_posix(): f.read_bytes()
                      for f in (p / 'licenses').rglob('*') if f.is_file()})
    manifest = dict(metadata, variant=variant, abi=4, hardware_tested=False,
                    cpu_sampling=False, scoped_worker_bigblock=0,
                    requires='Existing PES13 installation; quiet overlay requires PERF30 NRO',
                    files={name: sha(data) for name, data in files.items()})
    manifest_name = 'PERF30-manifest.json'
    files[manifest_name] = (json.dumps(manifest, indent=2) + '\n').encode()
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
    target = p / 'dist' / f'pes13-perf30-{variant}.zip'
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
                'same_math_and_copy_emitters_as_perf28', 'private_mesa_link_verified',
                'compiled_audio_and_mesa_diagnostics', 'mesa_original_untouched'):
        assert verified[key], key
    for name, digest in verified['changed_sources_sha256'].items():
        assert sha((p / name).read_bytes()) == digest, name
    nro = (w / 'payload' / prefix / 'pes13-nx.nro').read_bytes()
    assert sha(nro) == build['nro_sha256']
    meta = inspect_nro(nro, (p / 'assets/icon.jpg').read_bytes(), expected_title='PES13-NX PERF30')
    assert b'pes13-nx-0.2.0-perf30-submit-stages' in nro
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
    flag = prefix + 'perf30-submit-diagnostics.txt'
    main_files = dict(baseline)
    main_files[prefix + 'pes13-nx.nro'] = nro
    main_files[flag] = b'1\n'
    quiet = {cfg: baseline[cfg], profile: b'0\n', growth: b'0\n', flag: b'0\n'}
    # Rollback payload is exactly the previous control runtime. The PERF30 flag
    # may remain on SD; PERF29 does not read it. Main reinstall resets it to 1.
    rollback = dict(baseline)
    assert [n for n in baseline if baseline[n] != main_files[n]] == [prefix + 'pes13-nx.nro']
    assert set(main_files) - set(baseline) == {flag}
    assert sha(rollback[prefix + 'pes13-nx.nro']) == '83a3b78018e4f01afd27d46cb67b5046552f9b1596d9fab7efb985b1e0622cc5'
    rollback_meta = inspect_nro(rollback[prefix + 'pes13-nx.nro'], (p / 'assets/icon.jpg').read_bytes(),
                                expected_title='PES13-NX PERF29')
    for data, count in ((main_files, 1), (quiet, 0), (rollback, 1)):
        assert sum(n.endswith('.nro') for n in data) == count
        assert data[profile] == data[growth] == b'0\n'
        assert data[cfg].count(b'profile=0') == 1 and b'profile=1' not in data[cfg]
        assert not any(n.lower().endswith(('.exe', '.dat', '.reg', '.log', 'ntdll.dll')) for n in data)
        assert all('/users/' not in n for n in data)
    reports = [
        package('submit-diagnostics', main_files, dict(nro_metadata=meta, nro_sha256=sha(nro),
            diagnostic_only=True, submit_diagnostics=True, runtime_rebuilt=True)),
        package('quiet', quiet, dict(nro_metadata=None, diagnostic_only=True, submit_diagnostics=False,
            runtime_rebuilt=False)),
        package('rollback-perf29', rollback, dict(nro_metadata=rollback_meta,
            nro_sha256=sha(rollback[prefix + 'pes13-nx.nro']), exact_prior_control_payload=True,
            runtime_rebuilt=False)),
    ]
    (w / 'packages.json').write_text(json.dumps(reports, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(reports, indent=2))

if __name__ == '__main__':
    main()
