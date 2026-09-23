"""One NRO, a matched configuration control, and exact quiet PERF25 rollback."""
from pathlib import Path
import hashlib,json,zipfile
from nro_assets import inspect_nro
p=Path(__file__).resolve().parents[1];w=p/'local/perf26';prefix='switch/pes13-nx/'
sha=lambda b:hashlib.sha256(b).hexdigest()
build=json.loads((w/'build.json').read_text());v=json.loads((w/'verification.json').read_text())
assert build['source_restored'] and v['vendor_clean_at_pinned_revision']
assert v['same_generated_native_and_opcode_sources_as_perf25'] and v['compiled_scoped_env_and_trap_verified']
assert v['callret_tests']['emitted_return_and_stack_cap_cases']==816 and v['callret_tests']['trap_routing_cases']==9
for name,digest in v['changed_sources_sha256'].items():assert sha((p/name).read_bytes())==digest
nro=(w/'payload'/prefix/'pes13-nx.nro').read_bytes()
assert sha(nro)==build['nro_sha256'] and b'pes13-nx-0.2.0-perf26-callret' in nro
meta=inspect_nro(nro,(p/'assets/icon.jpg').read_bytes(),expected_title='PES13-NX PERF26')
prior=p/'dist/pes13-perf25-paircopy.zip'
assert sha(prior.read_bytes())=='ee8c5252a2a5cdb023b6682ca40e124ba2116f30c12dd3cc06bfb56f4bc737dc'
with zipfile.ZipFile(prior) as z:
    manifest=json.loads(z.read('PERF25-manifest.json'))
    files={n:z.read(n) for n in z.namelist() if n.startswith(prefix)}
assert all(sha(data)==manifest['files'][name] for name,data in files.items())
old=files[prefix+'pes13-nx.nro']
assert sha(old)=='888c77730685a8cff44edf2f07d3146352dbd29b986413a7b2697b20ce9d2d81'
assert sha(files[prefix+'drive_c/windows/system32/winebox64.dll'])=='42463d635af0874c301317c481eeb401d42963ef4d119059b3e309bb14f7a46b'
assert files[prefix+'profile.txt']==b'0\n'
assert b'profile=0' in files[prefix+'drive_c/PES13/pes2013.wine-nx.txt']
configs={};packages=[]
for variant in ('callret','control','rollback'):
    full=variant!='control';enabled=variant=='callret'
    data={k:v for k,v in files.items() if full or not k.endswith(('.dll','.nro'))}
    data[prefix+'perf26-callret.txt']=b'1\n' if enabled else b'0\n'
    if full:data[prefix+'pes13-nx.nro']=old if variant=='rollback' else nro
    configs[variant]={k:v for k,v in data.items() if not k.endswith(('.dll','.nro'))}
    data.update({'PERF26.md':(p/'docs/PERF26.md').read_bytes(),
        'PERF25-DIAGNOSTICS-RESULT.md':(p/'docs/PERF25-DIAGNOSTICS-RESULT.md').read_bytes()})
    if full:data['licenses/DXVK-LICENSE.txt']=(p/'licenses/DXVK-LICENSE.txt').read_bytes()
    assert sum(n.endswith('.nro') for n in data)==int(full)
    assert not any(n.endswith(('.exe','settings.dat','.log','ntdll.dll')) for n in data)
    data['PERF26-manifest.json']=json.dumps({'variant':variant,'abi':4,'hardware_tested':False,
        'game_callret':2 if enabled else 0,'global_callret':0,'cpu_sampling':False,
        'math':'SAFEFLAGS=2; scoped FASTROUND=1, X87DOUBLE=1; prior optimizations retained',
        'requires':'Existing PES13 install; control requires PERF26 NRO','startup_fix_claimed':False,
        'nro_metadata':meta if enabled else None,'files':{k:sha(v) for k,v in data.items()}},indent=2).encode()
    target=p/'dist'/f'pes13-perf26-{variant}.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for name,b in data.items():z.writestr(name,b)
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None and len(z.namelist())==len(data)
        assert all(z.read(name)==b for name,b in data.items())
    packages.append({'variant':variant,'path':str(target),'bytes':target.stat().st_size,'sha256':sha(target.read_bytes())})
assert [k for k,v in configs['callret'].items() if configs['control'][k]!=v]==[prefix+'perf26-callret.txt']
(w/'packages.json').write_text(json.dumps(packages,indent=2)+'\n')
print(json.dumps(packages,indent=2))
