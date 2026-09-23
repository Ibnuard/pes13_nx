"""Package the verified scoped-emitter change over the current-DXVK control."""
from pathlib import Path
import hashlib
import io
import json
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

p = Path(__file__).resolve().parents[1]
w = p / 'local/perf36'
prefix = 'switch/pes13-nx/'
sha = lambda b: hashlib.sha256(b).hexdigest()

def main():
    verify = json.loads((w / 'verification.json').read_text())
    for key in ('source_restored', 'fastnan_four_passes', 'dispatch_byte_identical_to_perf34',
                'scoped_policy_byte_identical_to_perf34'):
        assert verify[key] is True, key
    nro = (w / 'payload' / prefix / 'pes13-nx.nro').read_bytes()
    assert sha(nro) == json.loads((w / 'build.json').read_text())['nro_sha256']
    with ZipFile(p / 'dist/pes13-perf34-dxvk-current.zip') as z:
        assert z.testzip() is None
        manifest = json.loads(z.read('PERF34-manifest.json'))
        base = {n: z.read(n) for n in z.namelist() if n.startswith(prefix)}
        assert all(sha(b) == manifest['files'][n] for n, b in base.items())
        credits = {n: z.read(n) for n in z.namelist()
                   if n.startswith('licenses/') or n in ('LICENSE', 'THIRD_PARTY.md')}
    assert sha(base[prefix + 'pes13-nx.nro']) == '8254f3a800e986c16e543ca765999a31fb6c08e8abf36fbd60368b2eed17bd1a'
    assert sha(base[prefix + 'drive_c/PES13/d3d9.dll']) == '265888c31ca78dffa290c39cb7e50bfb02762590e41927906e46fb32f01497fa'
    results = []
    for variant in ('scoped-fastnan', 'diagnostics'):
        payload = dict(base)
        payload[prefix + 'pes13-nx.nro'] = nro
        changed = [prefix + 'pes13-nx.nro']
        if variant == 'diagnostics':
            for suffix in ('configuration.ini', 'drive_c/PES13/pes2013.wine-nx.txt'):
                name = prefix + suffix
                assert payload[name].count(b'profile=0') == 1
                payload[name] = payload[name].replace(b'profile=0', b'profile=1')
                changed.append(name)
        assert sorted(n for n in payload if payload[n] != base[n]) == sorted(changed)
        assert sum(n.endswith('.nro') for n in payload) == 1
        assert not any(n.lower().endswith(('.exe', '.dat', '.reg', '.log')) or '/users/' in n for n in payload)
        assert payload[prefix + 'drive_c/PES13/d3d9.dll'] == payload[prefix + 'drive_c/dxvk/d3d9.dll']
        files = dict(credits, **payload)
        for name in ('PERF36.md', 'PERF35-RESULT.md'):
            files[name] = (p / 'docs' / name).read_bytes()
        record = dict(variant=variant, base='PERF34 DXVK current', abi=manifest['abi'],
            nro_sha256=sha(nro), nro_metadata=verify['nro_metadata'],
            changed_runtime_files=changed, box64_global_preset_unchanged=True,
            inherited_perf33_scope_unchanged=True, dxvk=manifest['dxvk'],
            fastnan_sites=verify['fastnan_sites'], startup_fix_claimed=False,
            hardware_tested=False, target_match_fps=30, target_verified=False,
            files={n: sha(b) for n, b in sorted(files.items())})
        files['PERF36-manifest.json'] = (json.dumps(record, indent=2) + '\n').encode()
        buf = io.BytesIO()
        with ZipFile(buf, 'w', ZIP_DEFLATED) as z:
            for n, b in sorted(files.items()):
                assert not n.startswith('/') and '..' not in Path(n).parts
                info = ZipInfo(n, (2026, 9, 23, 0, 0, 0))
                info.compress_type = ZIP_DEFLATED
                z.writestr(info, b)
        raw = buf.getvalue()
        target = p / 'dist' / f'pes13-perf36-{variant}.zip'
        if target.exists():
            assert target.read_bytes() == raw, ('refusing changed package overwrite', target)
        else:
            with target.open('xb') as f: f.write(raw)
        with ZipFile(target) as z:
            assert z.testzip() is None and all(z.read(n) == b for n, b in files.items())
        results.append(dict(path=str(target), bytes=len(raw), sha256=sha(raw),
            nro_sha256=sha(nro), changed_runtime_files=changed, hardware_tested=False))
    (w / 'packages.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))

if __name__ == '__main__': main()
