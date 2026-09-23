"""Package the ABI-matched PERF15 pair and exact PERF14/ABI3 rollback."""
from pathlib import Path
import hashlib
import json
import zipfile
import pefile
from nro_assets import inspect_nro

p = Path(__file__).resolve().parents[1]
work = p/'local/perf15'
sha = lambda b: hashlib.sha256(b).hexdigest()
prefix = 'switch/pes13-nx/'
dll_path = 'drive_c/windows/system32/winebox64.dll'
legacy = p/'local/legacy-cleanup/wine/drive_c/windows/system32'
pair = json.loads((work/'pair.json').read_text())
assert pair['source_restored'] and pair['abi'] == 4 and pair['run_params_bytes'] == 56
new_nro = (work/'payload'/prefix/'pes13-nx.nro').read_bytes()
new_dll = (work/'payload'/prefix/dll_path).read_bytes()
old_nro = (p/'local/perf14/payload'/prefix/'pes13-nx.nro').read_bytes()
old_dll = (legacy/'winebox64.dll').read_bytes()
assert sha(new_nro) == pair['nro_sha256'] and sha(new_dll) == pair['dll_sha256']
assert sha(old_nro) == '7892860a4a410f8d5d5257b8018d46c873bf43f942c32ce2c3b4a0206a332f04'
assert sha(old_dll) == 'fec85ac6953057ab92483848cb2c8c2fca462fe8560b8729559718bc54ec2781'
(work/'rollback-winebox64.dll').write_bytes(old_dll)
(work/'rollback-perf14.nro').write_bytes(old_nro)
pe = pefile.PE(data=new_dll)
assert pe.FILE_HEADER.Machine == 0xaa64 and pe.OPTIONAL_HEADER.Magic == 0x20b
expected_exports = {s.name for s in pefile.PE(data=old_dll).DIRECTORY_ENTRY_EXPORT.symbols}
assert expected_exports == {s.name for s in pe.DIRECTORY_ENTRY_EXPORT.symbols}
imports = {}
for module in pe.DIRECTORY_ENTRY_IMPORT:
    name = module.dll.decode().lower()
    assert name in ('ntdll.dll', 'wow64.dll'), name
    dependency = p/'local/perf13/ntdll-suspend-backoff.dll' if name == 'ntdll.dll' else legacy/name
    dep = pefile.PE(str(dependency))
    names = {s.name for s in dep.DIRECTORY_ENTRY_EXPORT.symbols}
    ordinals = {s.ordinal for s in dep.DIRECTORY_ENTRY_EXPORT.symbols}
    imports[name] = []
    for entry in module.imports:
        assert entry.name in names if entry.name else entry.ordinal in ordinals, (name, entry.name)
        imports[name].append(entry.name.decode() if entry.name else entry.ordinal)
assert 'Wow64RaiseException' in imports['wow64.dll']
config = (p/'config/drive_c/PES13/pes2013.wine-nx.txt').read_bytes()
assert b'profile=0' in config and b'verbose=0' in config
output = []
for variant, nro, dll, title, marker, abi in (
    ('guest-exceptions', new_nro, new_dll, 'PES13-NX PERF15', 'pes13-nx-0.2.0-perf15-guest-exceptions', 4),
    ('rollback', old_nro, old_dll, 'PES13-NX PERF14', 'pes13-nx-0.2.0-perf14-map-guards', 3),
):
    assert marker.encode() in nro
    meta = inspect_nro(nro, (p/'assets/icon.jpg').read_bytes(), expected_title=title)
    files = {
        prefix+'pes13-nx.nro': nro, prefix+dll_path: dll,
        prefix+'profile.txt': b'0\n', prefix+'perf8-turbo.txt': b'0\n',
        prefix+'drive_c/PES13/pes2013.wine-nx.txt': config,
        'PERF15.md': (p/'docs/PERF15.md').read_bytes(),
    }
    assert [n for n in files if n.endswith('.dll')] == [prefix+dll_path]
    assert not any(n.endswith(('.exe', 'settings.dat', '.box64.txt')) for n in files)
    files['PERF15-manifest.json'] = json.dumps({
        'variant': variant, 'abi': abi, 'hardware_tested': False,
        'requires': 'PERF13/PERF14 installation; copy NRO and winebox64.dll together',
        'preserves': ['PERF13 ntdll', 'DXVK', 'Compatible preset', 'game', 'saves', 'controllers'],
        'nro': meta, 'new_imports_verified': imports,
        'files': {n: sha(b) for n,b in files.items()},
    }, indent=2).encode()
    target = p/'dist'/f'pes13-perf15-{variant}.zip'
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        for n,b in files.items(): z.writestr(n,b)
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None and set(z.namelist()) == set(files)
        assert all(z.read(n) == b for n,b in files.items())
    item = {'path': str(target), 'sha256': sha(target.read_bytes()), 'bytes': target.stat().st_size}
    output.append(item)
    print(json.dumps(item))
(work/'packages.json').write_text(json.dumps(output, indent=2))
