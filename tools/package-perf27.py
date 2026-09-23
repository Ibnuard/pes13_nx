"""Single NRO experiment, matched switch-off control, exact PERF26 rollback."""
from pathlib import Path
import hashlib,json,zipfile
from nro_assets import inspect_nro
p=Path(__file__).resolve().parents[1];w=p/'local/perf27';prefix='switch/pes13-nx/'
sha=lambda b:hashlib.sha256(b).hexdigest()
build=json.loads((w/'build.json').read_text());v=json.loads((w/'verification.json').read_text())
assert build['source_restored'] and v['vendor_clean_at_pinned_revision']
assert v['same_cpu_emitters_and_policy_as_perf26'] and v['linked_horizon_and_vulkan_hooks_verified']
for name,digest in v['changed_sources_sha256'].items():assert sha((p/name).read_bytes())==digest,name
nro=(w/'payload'/prefix/'pes13-nx.nro').read_bytes()
assert sha(nro)==build['nro_sha256'] and b'pes13-nx-0.2.0-perf27-wakes' in nro
meta=inspect_nro(nro,(p/'assets/icon.jpg').read_bytes(),expected_title='PES13-NX PERF27')
prior=p/'dist/pes13-perf26-callret.zip'
assert sha(prior.read_bytes())=='90731670a5b0e1a4db4a1876a8b9b6e8b69b36765c44aa60928904f1363ad44b'
with zipfile.ZipFile(prior) as z:
    manifest=json.loads(z.read('PERF26-manifest.json'))
    files={n:z.read(n) for n in z.namelist() if n.startswith(prefix)}
assert all(sha(b)==manifest['files'][n] for n,b in files.items())
assert sha(files[prefix+'pes13-nx.nro'])=='fd1fef0080f97916cc952879692ad5c485f6b2ecc85016cc0448ccce7fd73bcd'
assert files[prefix+'profile.txt']==b'0\n'
assert b'profile=0' in files[prefix+'drive_c/PES13/pes2013.wine-nx.txt']
assert files[prefix+'perf26-callret.txt']==b'1\n'
packages=[];configs={}
for variant in ('wakes','control','rollback'):
    full=variant!='control'
    data={n:b for n,b in files.items() if full or not n.endswith(('.nro','.dll'))}
    data[prefix+'perf27-targeted-wake.txt']=b'1\n' if variant=='wakes' else b'0\n'
    if variant=='wakes':data[prefix+'pes13-nx.nro']=nro
    configs[variant]={n:b for n,b in data.items() if not n.endswith(('.nro','.dll'))}
    data['PERF27.md']=(p/'docs/PERF27.md').read_bytes()
    if full:data['licenses/DXVK-LICENSE.txt']=(p/'licenses/DXVK-LICENSE.txt').read_bytes()
    assert sum(n.endswith('.nro') for n in data)==int(full)
    assert not any(n.endswith(('.exe','settings.dat','.log','ntdll.dll')) for n in data)
    if variant=='rollback':assert all(data[n]==b for n,b in files.items())
    data['PERF27-manifest.json']=json.dumps({'variant':variant,'abi':4,'hardware_tested':False,
        'targeted_wakes':variant=='wakes','cpu_preset':'same as PERF26','cpu_sampling':False,
        'requires':'Existing PES13 installation; control requires PERF27 NRO',
        'nro_metadata':meta if variant=='wakes' else None,
        'files':{n:sha(b) for n,b in data.items()}},indent=2).encode()
    target=p/'dist'/f'pes13-perf27-{variant}.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in data.items():z.writestr(n,b)
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None and len(z.namelist())==len(data)
        assert all(z.read(n)==b for n,b in data.items())
    packages.append({'variant':variant,'path':str(target),'bytes':target.stat().st_size,'sha256':sha(target.read_bytes())})
assert [n for n,b in configs['wakes'].items() if configs['control'][n]!=b]==[prefix+'perf27-targeted-wake.txt']
(w/'packages.json').write_text(json.dumps(packages,indent=2)+'\n')
print(json.dumps(packages,indent=2))
