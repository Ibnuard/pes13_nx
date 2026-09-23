"""Bundle tested runtime and DXVK artifacts without touching game data."""
from pathlib import Path
import hashlib
import json
import zipfile
from nro_assets import inspect_nro

project = Path(__file__).resolve().parents[1]
dist = project / 'dist'
prefix = 'switch/pes13-nx/'
digest = lambda data: hashlib.sha256(data).hexdigest()

def payload(name):
    with zipfile.ZipFile(dist / name) as z:
        assert z.testzip() is None
        return {n: z.read(n) for n in z.namelist() if n.startswith(prefix) and not n.endswith('/')}

for variant, runtime, dxvk in (
    ('combined', 'pes13-perf10-runtime.zip', 'pes13-perf10-dxvk311.zip'),
    ('full-rollback', 'pes13-perf8-overlay.zip', 'pes13-perf10-rollback.zip'),
):
    files = payload(runtime)
    files.update(payload(dxvk))
    nro = files[prefix + 'pes13-nx.nro']
    if variant == 'combined':
        assert b'pes13-nx-0.2.0-perf10-resume-gate' in nro
        inspect_nro(nro, (project / 'assets/icon.jpg').read_bytes(), expected_title='PES13-NX PERF10')
    else:
        assert digest(nro) == '8db297754d7b88f205f1f5abb678008fc2594dac793b61328c507514476d6edc'
    assert sum(n.endswith('.nro') for n in files) == 1
    assert not any(n.endswith(('settings.dat', 'pes2013.exe', 'rld.dll')) for n in files)
    files['PERF10-START-HERE.md'] = (project / 'docs/PERF10-RUNTIME.md').read_bytes()
    files['PERF10-DXVK.md'] = (project / 'docs/PERF10.md').read_bytes()
    files['licenses/DXVK-LICENSE.txt'] = (project / 'licenses/DXVK-LICENSE.txt').read_bytes()
    files['PERF10-manifest.json'] = json.dumps({
        'variant': variant, 'hardware_tested': False,
        'sources': [runtime, dxvk],
        'source_hashes': {n: digest((dist / n).read_bytes()) for n in (runtime, dxvk)},
        'files': {n: digest(b) for n, b in files.items()},
    }, indent=2).encode()
    output = dist / f'pes13-perf10-{variant}.zip'
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    with zipfile.ZipFile(output) as z:
        assert z.testzip() is None
        for name, data in files.items():
            assert z.read(name) == data
    print(output, digest(output.read_bytes()))
