"""Preserve PERF15; package 3D sampling and WineD3D vs DXVK controls."""
from pathlib import Path
import hashlib, json, os, subprocess, sys, tarfile, zipfile
import pefile

p = Path(__file__).resolve().parents[1]
work = p/'local/perf16'
work.mkdir(parents=True, exist_ok=True)
legacy = p/'local/legacy-cleanup/wine'
prefix = 'switch/pes13-nx/'
sha = lambda b: hashlib.sha256(b).hexdigest()
reference = json.loads((p/'local/perf15/pair.json').read_text())
for rel, key in (('pes13-nx.nro', 'nro_sha256'), ('drive_c/windows/system32/winebox64.dll', 'dll_sha256')):
    assert sha((p/'local/perf15/payload'/prefix/rel).read_bytes()) == reference[key]

manifest = {v['path']:v['sha256'] for v in json.loads((p/'config/runtime-files.json').read_text())}
for rel in ('drive_c/windows/syswow64/d3d9.dll', 'drive_c/windows/syswow64/wined3d.dll',
            'drive_c/windows/syswow64/opengl32.dll'):
    assert sha((legacy/rel).read_bytes()) == manifest[rel], rel
wine_dll = (legacy/'drive_c/windows/syswow64/d3d9.dll').read_bytes()
archive = p/'local/perf10/dxvk-3.1.1.tar.gz'
assert sha(archive.read_bytes()) == '40565b4a724aadc4433fa4e010b4b23916d9b1f1baeee64e17186db94f54e608'
with tarfile.open(archive) as tar:
    dxvk_dll = tar.extractfile('dxvk-3.1.1/x32/d3d9.dll').read()
for data in (wine_dll, dxvk_dll):
    pe = pefile.PE(data=data)
    assert pe.FILE_HEADER.Machine == 0x14c
    assert {b'Direct3DCreate9', b'Direct3DCreate9Ex'} <= {s.name for s in pe.DIRECTORY_ENTRY_EXPORT.symbols}

# Read-only hardlinks to dependency inputs, never written through. The sole
# changing file is a separately created app-local D3D9 DLL in this test stage.
stage = work/'import-stage'
for folder in ('syswow64', 'system32'):
    out = stage/'drive_c/windows'/folder
    out.mkdir(parents=True, exist_ok=True)
    for source in (legacy/'drive_c/windows'/folder).glob('*.dll'):
        target = out/source.name
        if not target.exists(): os.link(source, target)
        assert target.read_bytes() == source.read_bytes()
(stage/'drive_c/PES13').mkdir(parents=True, exist_ok=True)
(stage/'drive_c/dxvk').mkdir(parents=True, exist_ok=True)
import_results = {}
for name, dll in (('dxvk311', dxvk_dll), ('wined3d', wine_dll)):
    (stage/'drive_c/PES13/d3d9.dll').write_bytes(dll)
    report = work/f'imports-{name}.json'
    result = subprocess.run([sys.executable, str(p/'tools/check_payload.py'), str(stage),
        '--entry', 'd3d9.dll', '--dxvk', '--output', str(report)], capture_output=True, text=True)
    assert result.returncode in (0,1) and report.exists(), result.stdout+result.stderr
    issues = json.loads(report.read_text())['issues']
    required = [i for i in issues if not i.get('deferred',False)]
    assert not required, required
    import_results[name] = {'required_issues':len(required), 'deferred_issues':len(issues),
        'full_static_check_passed':not issues}
    print(f'{name}: required PE32 imports resolved; {len(issues)} optional/deferred issues')

config = (p/'config/drive_c/PES13/pes2013.wine-nx.txt').read_text()
assert config.count('profile=0') == 1 and config.count('d3d9=dxvk') == 1
assert 'verbose=0' in config
packages = []
for variant in ('sample-3d', 'wined3d', 'restore-dxvk'):
    sample = variant == 'sample-3d'
    is_wine = variant == 'wined3d'
    selected = config.replace('profile=0', f'profile={int(sample)}')
    if is_wine: selected = selected.replace('d3d9=dxvk', 'd3d9=wine')
    files = {
        prefix+'profile.txt': f'{int(sample)}\n'.encode(),
        prefix+'perf8-turbo.txt': b'0\n',
        prefix+'drive_c/PES13/pes2013.wine-nx.txt': selected.encode(),
        'PERF16.md': (p/'docs/PERF16.md').read_bytes(),
        'PERF15-RESULT.md': (p/'docs/PERF15-RESULT.md').read_bytes(),
    }
    if not sample:
        files[prefix+'drive_c/PES13/d3d9.dll'] = wine_dll if is_wine else dxvk_dll
        files['licenses/Wine-LICENSE.txt' if is_wine else 'licenses/DXVK-LICENSE.txt'] = (
            (p/'LICENSE') if is_wine else (p/'licenses/DXVK-LICENSE.txt')).read_bytes()
    if is_wine:
        files[prefix+'drive_c/PES13/pes2013.csmt.txt'] = b'1\n'
    assert not any(n.endswith(('.nro', '.exe', 'winebox64.dll', 'ntdll.dll', 'settings.dat', '.box64.txt')) for n in files)
    assert [n for n in files if n.endswith('.dll')] == ([] if sample else [prefix+'drive_c/PES13/d3d9.dll'])
    files['PERF16-manifest.json'] = json.dumps({
        'variant':variant, 'sampling':sample, 'hardware_tested':False,
        'requires':'Existing PERF15 NRO/ABI4 pair and base Wine dependencies',
        'stable_pair':reference,
        'Wine_D3D9_sha256':sha(wine_dll), 'DXVK_3_1_1_sha256':sha(dxvk_dll),
        'base_Wine_dependencies':{rel:manifest[rel] for rel in (
            'drive_c/windows/syswow64/wined3d.dll', 'drive_c/windows/syswow64/opengl32.dll')},
        'required_imports_checked':True,
        'import_results':import_results,
        'files':{n:sha(b) for n,b in files.items()},
    }, indent=2).encode()
    target = p/'dist'/f'pes13-perf16-{variant}.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        for n,b in files.items(): z.writestr(n,b)
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None and set(z.namelist()) == set(files)
        assert all(z.read(n) == b for n,b in files.items())
    packages.append({'path':str(target), 'sha256':sha(target.read_bytes()), 'bytes':target.stat().st_size})
(work/'packages.json').write_text(json.dumps(packages, indent=2))
print(json.dumps(packages, indent=2))
