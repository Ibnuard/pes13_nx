"""Package the PERF17 experiment, same-NRO control and exact PERF15 rollback."""
from pathlib import Path
import hashlib
import json
import zipfile
from nro_assets import inspect_nro

p = Path(__file__).resolve().parents[1]
work = p / 'local/perf17'
prefix = 'switch/pes13-nx/'
sha = lambda b: hashlib.sha256(b).hexdigest()
pair = json.loads((p / 'local/perf15/pair.json').read_text())
build = json.loads((work / 'build.json').read_text())
assert pair['abi'] == 4 and build['source_restored']
stable = p / 'local/perf15/payload' / prefix
old_nro = (stable / 'pes13-nx.nro').read_bytes()
dll = (stable / 'drive_c/windows/system32/winebox64.dll').read_bytes()
assert sha(old_nro) == pair['nro_sha256'] == 'dd9bf1541ddb4e4cde9a22f806e5a93c80077afb47052e6402def16cc8a5729b'
assert sha(dll) == pair['dll_sha256'] == '42463d635af0874c301317c481eeb401d42963ef4d119059b3e309bb14f7a46b'
new_nro = (work / 'payload' / prefix / 'pes13-nx.nro').read_bytes()
assert sha(new_nro) == build['nro_sha256']
assert b'pes13-nx-0.2.0-perf17-hotblocks' in new_nro and b'[PERF17-BLOCK]' in new_nro
meta = inspect_nro(new_nro, (p / 'assets/icon.jpg').read_bytes(), expected_title='PES13-NX PERF17')
restore = p / 'dist/pes13-perf16-restore-dxvk.zip'
assert sha(restore.read_bytes()) == '6c68dac93db95c8b78e6c88650e556e1214a0b0d7a9a9477a18e8e263f042cc5'
with zipfile.ZipFile(restore) as z:
    reference = json.loads(z.read('PERF16-manifest.json'))
    dxvk = z.read(prefix + 'drive_c/PES13/d3d9.dll')
assert sha(dxvk) == reference['DXVK_3_1_1_sha256']
config = (p / 'config/drive_c/PES13/pes2013.wine-nx.txt').read_bytes()
assert b'profile=0' in config and b'verbose=0' in config and b'd3d9=dxvk' in config
packages = []
for variant in ('hotblocks', 'control', 'rollback'):
    files = {
        prefix + 'perf17-hotblocks.txt': b'1\n' if variant == 'hotblocks' else b'0\n',
        prefix + 'perf17-capture.txt': b'0\n' if variant == 'rollback' else b'1\n',
        prefix + 'profile.txt': b'0\n', prefix + 'perf8-turbo.txt': b'0\n',
        prefix + 'drive_c/PES13/pes2013.wine-nx.txt': config,
        'PERF17.md': (p / 'docs/PERF17.md').read_bytes(),
    }
    if variant != 'control':
        files.update({
            prefix + 'pes13-nx.nro': old_nro if variant == 'rollback' else new_nro,
            prefix + 'drive_c/windows/system32/winebox64.dll': dll,
            prefix + 'drive_c/PES13/d3d9.dll': dxvk,
            'licenses/DXVK-LICENSE.txt': (p / 'licenses/DXVK-LICENSE.txt').read_bytes(),
        })
    assert not any(n.endswith(('.exe', 'settings.dat', 'ntdll.dll', '.box64.txt')) for n in files)
    files['PERF17-manifest.json'] = json.dumps({
        'variant': variant, 'abi': 4, 'hardware_tested': False,
        'requires': 'Existing stable PERF15 installation; control additionally requires PERF17 NRO',
        'continuous_sampling': False, 'scoped_bigblock': variant == 'hotblocks',
        'preserves': ['game', 'saves', 'settings.dat', 'controllers', 'ntdll', 'global Compatible preset'],
        'nro': meta if variant == 'hotblocks' else None,
        'files': {n: sha(b) for n, b in files.items()},
    }, indent=2).encode()
    target = p / 'dist' / f'pes13-perf17-{variant}.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items(): z.writestr(name, data)
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None and set(z.namelist()) == set(files)
        assert all(z.read(name) == data for name, data in files.items())
    packages.append({'path': str(target), 'sha256': sha(target.read_bytes()), 'bytes': target.stat().st_size})
(work / 'packages.json').write_text(json.dumps(packages, indent=2) + '\n')
print(json.dumps(packages, indent=2))
