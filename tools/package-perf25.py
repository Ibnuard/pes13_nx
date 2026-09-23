"""One-NRO pair-copy package, matched control, sampling overlay and rollback."""
from pathlib import Path
import hashlib,json,zipfile
from nro_assets import inspect_nro
p=Path(__file__).resolve().parents[1];w=p/'local/perf25';prefix='switch/pes13-nx/'
sha=lambda b:hashlib.sha256(b).hexdigest()
build=json.loads((w/'build.json').read_text());verify=json.loads((w/'verification.json').read_text())
assert build['source_restored'] and verify['math_emitters_identical_to_perf24']
assert verify['four_pass_compiled_copy_hook'] and verify['vendor_clean_at_pinned_revision']
assert verify['opcode00_only_scoped_paircopy_changed'] and verify['startup_slot_reserved']
assert verify['copy_tests']['cases']==2173 and verify['copy_tests']['page_fault_cases']==30
for name,digest in verify['copy_tests']['source_sha256'].items():assert sha((p/name).read_bytes())==digest
nro=(w/'payload'/prefix/'pes13-nx.nro').read_bytes()
assert sha(nro)==build['nro_sha256'] and b'pes13-nx-0.2.0-perf25-paircopy' in nro
assert all(s in nro for s in (b'[PERF25]',b'[FRAME24]',b'[PERF21]',b'[PERF22]',b'[RUN23]'))
meta=inspect_nro(nro,(p/'assets/icon.jpg').read_bytes(),expected_title='PES13-NX PERF25')
prior=p/'dist/pes13-perf24-diagnostics.zip'
assert sha(prior.read_bytes())=='08d36fd8128d6de8e6865d4b56abd792d25dba37484b52a6601aa9852ca4c245'
with zipfile.ZipFile(prior) as z:
    manifest=json.loads(z.read('PERF24-manifest.json'))
    imported={n:z.read(n) for n in (prefix+'pes13-nx.nro',prefix+'drive_c/windows/system32/winebox64.dll',prefix+'drive_c/PES13/d3d9.dll')}
assert all(sha(b)==manifest['files'][n] for n,b in imported.items())
old=imported[prefix+'pes13-nx.nro']
assert sha(old)=='85b8d20bcf24843f9d0bfebdcb757044cad7f05b17f1aca842a6a4d14c4952a0'
assert sha(imported[prefix+'drive_c/windows/system32/winebox64.dll'])=='42463d635af0874c301317c481eeb401d42963ef4d119059b3e309bb14f7a46b'
config=(p/'config/drive_c/PES13/pes2013.wine-nx.txt').read_bytes()
box=(p/'config/drive_c/PES13/pes2013.box64.txt').read_bytes()
settings=dict(line.split('=',1) for line in box.decode().splitlines() if line.startswith('BOX64_'))
assert settings=={'BOX64_DYNAREC_'+k:str(v) for k,v in {'SAFEFLAGS':2,'FASTNAN':0,'FASTROUND':0,'X87DOUBLE':1,'BIGBLOCK':0,'STRONGMEM':1,'CALLRET':0}.items()}
assert config.count(b'profile=0')==1 and b'verbose=0' in config and b'd3d9=dxvk' in config
packages=[];configs={}
for variant in ('paircopy','control','diagnostics','rollback'):
    sampled=variant=='diagnostics';copy=variant in ('paircopy','diagnostics');full=variant in ('paircopy','rollback')
    files={prefix+'profile.txt':b'1\n' if sampled else b'0\n',prefix+'production.txt':b'1\n',
        prefix+'no-balance.txt':b'0\n',prefix+'perf23-balance.txt':b'1\n',prefix+'perf22-floatmath.txt':b'0\n',
        prefix+'perf21-fastmath.txt':b'1\n',prefix+'perf20-fusion.txt':b'1\n',prefix+'perf19-matrix.txt':b'1\n',
        prefix+'perf17-hotblocks.txt':b'0\n',prefix+'perf17-capture.txt':b'1\n',prefix+'perf18-roundguard.txt':b'0\n',
        prefix+'perf8-turbo.txt':b'0\n',prefix+'perf25-paircopy.txt':b'1\n' if copy else b'0\n',
        prefix+'drive_c/PES13/pes2013.box64.txt':box,
        prefix+'drive_c/PES13/pes2013.wine-nx.txt':config.replace(b'profile=0',b'profile=1') if sampled else config,
        'PERF25.md':(p/'docs/PERF25.md').read_bytes(),'PERF24-RESULT.md':(p/'docs/PERF24-RESULT.md').read_bytes()}
    configs[variant]={k:v for k,v in files.items() if k.startswith(prefix)}
    if full:
        files.update(imported);files[prefix+'pes13-nx.nro']=old if variant=='rollback' else nro
        files['licenses/DXVK-LICENSE.txt']=(p/'licenses/DXVK-LICENSE.txt').read_bytes()
    assert sum(n.endswith('.nro') for n in files)==int(full)
    assert not any(n.endswith(('.exe','settings.dat','ntdll.dll','.log')) for n in files)
    files['PERF25-manifest.json']=json.dumps({'variant':variant,'abi':4,'hardware_tested':False,
        'requires':'Existing PES13 install; control and diagnostics require PERF25 NRO',
        'copy_loop':copy,'sampling':sampled,'sampling_cadence':'20 ms during 2s/10s when enabled',
        'math':'scoped FASTROUND=1, X87DOUBLE=1, SAFEFLAGS=2; PERF19/20 retained',
        'startup_fix_claimed':False,'history':4,'nro_metadata':meta if variant=='paircopy' else None,
        'files':{k:sha(v) for k,v in files.items()}},indent=2).encode()
    target=p/'dist'/f'pes13-perf25-{variant}.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in files.items():z.writestr(name,data)
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None and len(z.namelist())==len(files)
        assert all(z.read(name)==data for name,data in files.items())
    packages.append({'path':str(target),'bytes':target.stat().st_size,'sha256':sha(target.read_bytes()),'variant':variant})
assert [k for k,v in configs['paircopy'].items() if configs['control'][k]!=v]==[prefix+'perf25-paircopy.txt']
assert set(k for k,v in configs['paircopy'].items() if configs['diagnostics'][k]!=v)=={prefix+'profile.txt',prefix+'drive_c/PES13/pes2013.wine-nx.txt'}
(w/'packages.json').write_text(json.dumps(packages,indent=2)+'\n')
print(json.dumps(packages,indent=2))
