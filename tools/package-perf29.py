"""One NRO, a single-variable control, optional sampling, exact PERF28 rollback."""
from pathlib import Path
import hashlib,json,zipfile
from nro_assets import inspect_nro
p=Path(__file__).resolve().parents[1];w=p/'local/perf29';prefix='switch/pes13-nx/'
sha=lambda b:hashlib.sha256(b).hexdigest()
build=json.loads((w/'build.json').read_text());v=json.loads((w/'verification.json').read_text())
status=json.loads((w/'build-status.json').read_text());assert status['state']=='complete' and status['restored']
for key in ('source_restored','vendor_clean_at_pinned_revision','compiled_scoped_block_policy_and_copy_hooks',
            'same_math_and_copy_emitters_as_perf28','same_horizon_vulkan_fault_capture_as_perf28'):
    assert v[key],key
for path,digest in v['changed_sources_sha256'].items(): assert sha((p/path).read_bytes())==digest,path
nro=(w/'payload'/prefix/'pes13-nx.nro').read_bytes();assert sha(nro)==build['nro_sha256']
meta=inspect_nro(nro,(p/'assets/icon.jpg').read_bytes(),expected_title='PES13-NX PERF29')
assert b'pes13-nx-0.2.0-perf29-worker-blocks' in nro
prior=p/'dist/pes13-perf28-diagnostics.zip'
assert sha(prior.read_bytes())=='30df34bf3586da928cf2d9068b0c78993ac52750cb71f9f7ec8f5c5a7a010362'
with zipfile.ZipFile(prior) as z:
    manifest=json.loads(z.read('PERF28-manifest.json'))
    files={n:z.read(n) for n in z.namelist() if n.startswith(prefix)}
assert all(sha(b)==manifest['files'][n] for n,b in files.items())
assert sha(files[prefix+'pes13-nx.nro'])=='312b0b842e672e66a70fab992604821d424933680fc8954520cb7e7b2f14ab3d'
cfg=prefix+'drive_c/PES13/pes2013.wine-nx.txt';flag=prefix+'perf29-worker-blocks.txt'
assert files[prefix+'profile.txt']==b'1\n' and files[cfg].count(b'profile=1')==1
packages=[];contents={}
for variant in ('worker-blocks','control','sampling','rollback'):
    full=variant in ('worker-blocks','rollback');sampling=variant in ('sampling','rollback')
    data={n:b for n,b in files.items() if full or n in (prefix+'profile.txt',cfg)}
    if variant!='rollback':
        if full: data[prefix+'pes13-nx.nro']=nro
        data[prefix+'profile.txt']=b'1\n' if sampling else b'0\n'
        data[cfg]=files[cfg] if sampling else files[cfg].replace(b'profile=1',b'profile=0')
        data[flag]=b'0\n' if variant=='control' else b'1\n'
    else: assert data==files
    contents[variant]=dict(data)
    assert sum(n.endswith('.nro') for n in data)==int(full)
    assert not any(n.endswith(('.exe','settings.dat','.log','ntdll.dll')) for n in data)
    data['PERF29.md']=(p/'docs/PERF29.md').read_bytes()
    if full:data['licenses/DXVK-LICENSE.txt']=(p/'licenses/DXVK-LICENSE.txt').read_bytes()
    data['PERF29-manifest.json']=json.dumps({'variant':variant,'abi':4,'hardware_tested':False,
        'cpu_sampling':sampling,'scoped_worker_bigblock':1 if variant in ('worker-blocks','sampling') else 0,
        'requires':'Existing PES13 installation; config-only overlays require PERF29 NRO',
        'nro_metadata':meta if variant=='worker-blocks' else None,
        'files':{n:sha(b) for n,b in data.items()}},indent=2).encode()
    target=p/'dist'/f'pes13-perf29-{variant}.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in data.items():z.writestr(n,b)
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None and len(z.namelist())==len(data)
        assert all(z.read(n)==b for n,b in data.items())
    packages.append({'variant':variant,'path':str(target),'bytes':target.stat().st_size,'sha256':sha(target.read_bytes())})
assert set(contents['control'])=={prefix+'profile.txt',cfg,flag}
assert [n for n,b in contents['control'].items() if b!=contents['worker-blocks'][n]]==[flag]
assert contents['sampling'][flag]==contents['worker-blocks'][flag]
assert contents['sampling'][cfg].replace(b'profile=1',b'profile=0')==contents['worker-blocks'][cfg]
(w/'packages.json').write_text(json.dumps(packages,indent=2)+'\n')
print(json.dumps(packages,indent=2))
