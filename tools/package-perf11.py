"""Package the Box64 update independently of DXVK, with PERF10 rollback."""
from pathlib import Path
import hashlib
import json
import zipfile
from nro_assets import inspect_nro

p = Path(__file__).resolve().parents[1]
prefix = 'switch/pes13-nx/'
sha = lambda b: hashlib.sha256(b).hexdigest()
expected = (p / 'dist/pes13-perf8-overlay' / prefix / 'drive_c/PES13/pes2013.box64.txt').read_bytes()
for variant, source, title, marker in (
    ('box64', 'pes13-perf11-runtime.zip', 'PES13-NX PERF11', 'pes13-nx-0.2.0-perf11-box64-044'),
    ('rollback', 'pes13-perf10-runtime.zip', 'PES13-NX PERF10', 'pes13-nx-0.2.0-perf10-resume-gate'),
):
    with zipfile.ZipFile(p / 'dist' / source) as z:
        assert z.testzip() is None
        files = {n: z.read(n) for n in z.namelist()
                 if n.startswith(prefix) and not n.endswith('/') and not n.endswith('dxvk.conf')}
    assert files[prefix+'drive_c/PES13/pes2013.box64.txt'] == expected
    nro = files[prefix+'pes13-nx.nro']
    assert marker.encode() in nro
    inspect_nro(nro, (p/'assets/icon.jpg').read_bytes(), expected_title=title)
    files[prefix+'profile.txt'] = b'0\n'
    files[prefix+'drive_c/PES13/pes2013.wine-nx.txt'] = (p/'config/drive_c/PES13/pes2013.wine-nx.txt').read_bytes()
    assert not any(n.endswith(('d3d9.dll','settings.dat','pes2013.exe','rld.dll')) for n in files)
    files['PERF11.md'] = (p/'docs/PERF11.md').read_bytes()
    files['PERF11-dependencies.json'] = (p/'config/perf11-dependencies.json').read_bytes()
    files['PERF11-manifest.json'] = json.dumps({
        'variant': variant, 'box64_commit': '2f130fab1d6e1a4ee8a71dc60cfdfcc839ad192a' if variant == 'box64' else 'dae0917c47b4edd8956f314210417a20fd225c4b',
        'preset_unchanged': True, 'hardware_tested': False,
        'files': {n:sha(b) for n,b in files.items()},
    },indent=2).encode()
    output = p/'dist'/f'pes13-perf11-{variant}.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in files.items(): z.writestr(name,data)
    with zipfile.ZipFile(output) as z:
        assert z.testzip() is None
        assert all(z.read(n)==b for n,b in files.items())
    print(output,sha(output.read_bytes()))
