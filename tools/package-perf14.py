"""NRO-only mapping experiment and exact previous-NRO rollback."""
from pathlib import Path
import hashlib
import json
import zipfile
from nro_assets import inspect_nro

p = Path(__file__).resolve().parents[1]
sha = lambda b: hashlib.sha256(b).hexdigest()
new = (p/'local/perf14/payload/switch/pes13-nx/pes13-nx.nro').read_bytes()
old = (p/'local/perf14/rollback-perf11.nro').read_bytes()
assert sha(old) == '98ce549f65046fa44457dc36508cc1e5c65019cb94156e706e6d109ed64190f4'
assert sha(new) == json.loads((p/'local/perf14/build.json').read_text())['nro_sha256']
assert b'pes13-nx-0.2.0-perf14-map-guards' in new
assert b'pes13-nx-0.2.0-perf11-box64-044' in old
prefix = 'switch/pes13-nx/'
config = (p/'config/drive_c/PES13/pes2013.wine-nx.txt').read_bytes()
assert b'profile=0' in config and b'verbose=0' in config
for variant, nro, title in (('map-guards', new, 'PES13-NX PERF14'),
                            ('rollback-nro', old, 'PES13-NX PERF11')):
    meta = inspect_nro(nro, (p/'assets/icon.jpg').read_bytes(), expected_title=title)
    files = {
        prefix+'pes13-nx.nro': nro,
        prefix+'profile.txt': b'0\n', prefix+'perf8-turbo.txt': b'0\n',
        prefix+'drive_c/PES13/pes2013.wine-nx.txt': config,
        'PERF14.md': (p/'docs/PERF14.md').read_bytes(),
        'PERF13-RESULT.md': (p/'docs/PERF13-RESULT.md').read_bytes(),
    }
    files['PERF14-manifest.json'] = json.dumps({
        'variant': variant, 'hardware_tested': False,
        'requires': 'Existing PERF13 installation; keeps its ARM64 DLL',
        'nro': meta, 'rollback_byte_identical': True,
        'test_nro_sha256': sha(new), 'rollback_nro_sha256': sha(old),
        'files': {n: sha(b) for n,b in files.items()},
    }, indent=2).encode()
    assert not any(n.lower().endswith(('.dll', '.exe', 'settings.dat', '.box64.txt')) for n in files)
    target = p/'dist'/f'pes13-perf14-{variant}.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        for n,b in files.items(): z.writestr(n,b)
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None and set(z.namelist()) == set(files)
        assert all(z.read(n) == b for n,b in files.items())
    print(target, sha(target.read_bytes()), target.stat().st_size)
