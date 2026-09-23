"""One-NRO diagnostics, same-NRO sampler-off option, and exact PERF27 rollback."""
from pathlib import Path
import hashlib, json, zipfile
from nro_assets import inspect_nro
p = Path(__file__).resolve().parents[1]; w = p/'local/perf28'; prefix='switch/pes13-nx/'
sha = lambda b: hashlib.sha256(b).hexdigest()
build = json.loads((w/'build.json').read_text()); v = json.loads((w/'verification.json').read_text())
assert build['source_restored'] and v['vendor_clean_at_pinned_revision']
assert v['same_cpu_emitters_as_perf27'] and v['same_horizon_and_vulkan_as_perf27'] and v['compiled_fault_hook']
for name, digest in v['changed_sources_sha256'].items(): assert sha((p/name).read_bytes()) == digest, name
nro = (w/'payload'/prefix/'pes13-nx.nro').read_bytes()
assert sha(nro) == build['nro_sha256'] and b'pes13-nx-0.2.0-perf28-diagnostics' in nro
meta = inspect_nro(nro, (p/'assets/icon.jpg').read_bytes(), expected_title='PES13-NX PERF28')
prior = p/'dist/pes13-perf27-wakes.zip'
assert sha(prior.read_bytes()) == 'a5d58a48280a5609f099fd9e6e94d5d0a95f93c7a6169c41e64d2f77703bc693'
with zipfile.ZipFile(prior) as z:
    manifest = json.loads(z.read('PERF27-manifest.json'))
    files = {n:z.read(n) for n in z.namelist() if n.startswith(prefix)}
assert all(sha(b) == manifest['files'][n] for n,b in files.items())
assert sha(files[prefix+'pes13-nx.nro']) == '16a8f02fdc939839875c135421f0a5ced5ac85e9288af717aa8925bc825e42e1'
assert files[prefix+'profile.txt'] == b'0\n'
cfg = prefix+'drive_c/PES13/pes2013.wine-nx.txt'
assert files[cfg].count(b'profile=0') == 1
packages=[]; configs={}
for variant in ('diagnostics','quiet','rollback'):
    full = variant != 'quiet'; sampling = variant == 'diagnostics'
    data = {n:b for n,b in files.items() if full or n in (prefix+'profile.txt',cfg)}
    if variant == 'diagnostics':
        data[prefix+'pes13-nx.nro'] = nro
        data[prefix+'profile.txt'] = b'1\n'
        data[cfg] = files[cfg].replace(b'profile=0',b'profile=1')
    configs[variant] = {n:b for n,b in data.items() if not n.endswith(('.nro','.dll'))}
    data['PERF28.md'] = (p/'docs/PERF28.md').read_bytes()
    if full: data['licenses/DXVK-LICENSE.txt'] = (p/'licenses/DXVK-LICENSE.txt').read_bytes()
    assert sum(n.endswith('.nro') for n in data) == int(full)
    assert not any(n.endswith(('.exe','settings.dat','.log','ntdll.dll')) for n in data)
    if variant == 'rollback': assert all(data[n] == b for n,b in files.items())
    data['PERF28-manifest.json'] = json.dumps({'variant':variant,'abi':4,'hardware_tested':False,
        'diagnostic_only':True,'cpu_preset':'same as PERF27','cpu_sampling':sampling,
        'requires':'Existing PES13 installation; quiet requires PERF28 NRO',
        'nro_metadata':meta if variant=='diagnostics' else None,
        'files':{n:sha(b) for n,b in data.items()}},indent=2).encode()
    target = p/'dist'/f'pes13-perf28-{variant}.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in data.items(): z.writestr(n,b)
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None and len(z.namelist()) == len(data)
        assert all(z.read(n) == b for n,b in data.items())
    packages.append({'variant':variant,'path':str(target),'bytes':target.stat().st_size,'sha256':sha(target.read_bytes())})
assert set(configs['quiet']) == {prefix+'profile.txt',cfg}
assert configs['diagnostics'][cfg].replace(b'profile=1',b'profile=0') == configs['quiet'][cfg]
assert all(configs['diagnostics'][n] == b for n,b in files.items()
           if not n.endswith(('.nro','.dll')) and n not in (prefix+'profile.txt',cfg))
(w/'packages.json').write_text(json.dumps(packages,indent=2)+'\n')
print(json.dumps(packages,indent=2))
