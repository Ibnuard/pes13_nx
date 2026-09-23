"""PERF23 transition-balancing package, isolated controls and PERF21 fallback."""
from pathlib import Path
import hashlib,json,zipfile
from nro_assets import inspect_nro

p=Path(__file__).resolve().parents[1]; w=p/'local/perf23'; prefix='switch/pes13-nx/'
sha=lambda data:hashlib.sha256(data).hexdigest()
build=json.loads((w/'build.json').read_text()); assert build['source_restored']
verify=json.loads((w/'verification.json').read_text())
assert verify['math_emitters_identical_to_perf22'] and verify['native_dynarec_identical_to_perf22']
nro=(w/'payload'/prefix/'pes13-nx.nro').read_bytes()
assert sha(nro)==build['nro_sha256'] and b'pes13-nx-0.2.0-perf23-transitions' in nro
assert all(tag in nro for tag in (b'[PERF19]',b'[PERF20]',b'[PERF21]',b'[PERF22]',b'[PERF23]',b'[BALANCE23]',b'[RUN23]',b'[WATCH23]',b'[AFF23]'))
meta=inspect_nro(nro,(p/'assets/icon.jpg').read_bytes(),expected_title='PES13-NX PERF23')
prior=p/'dist/pes13-perf21-fastmath.zip'
assert sha(prior.read_bytes())=='3afde544594b741b854c02ca3439a73fd990150e4d5738351a5fa86eb0136aeb'
with zipfile.ZipFile(prior) as z:
    manifest=json.loads(z.read('PERF21-manifest.json'))
    old=z.read(prefix+'pes13-nx.nro')
    dll=z.read(prefix+'drive_c/windows/system32/winebox64.dll')
    dxvk=z.read(prefix+'drive_c/PES13/d3d9.dll')
assert sha(old)=='c992da989173dba2562c5719dc29834b7781e229e18fa7fffc0f711f6b0b6741'
assert sha(dll)==manifest['files'][prefix+'drive_c/windows/system32/winebox64.dll']=='42463d635af0874c301317c481eeb401d42963ef4d119059b3e309bb14f7a46b'
assert sha(dxvk)==manifest['files'][prefix+'drive_c/PES13/d3d9.dll']
config=(p/'config/drive_c/PES13/pes2013.wine-nx.txt').read_bytes()
boxconfig=(p/'config/drive_c/PES13/pes2013.box64.txt').read_bytes()
settings=dict(line.split('=',1) for line in boxconfig.decode().splitlines() if line.startswith('BOX64_'))
assert settings=={'BOX64_DYNAREC_'+k:str(v) for k,v in {'SAFEFLAGS':2,'FASTNAN':0,'FASTROUND':0,'X87DOUBLE':1,'BIGBLOCK':0,'STRONGMEM':1,'CALLRET':0}.items()}
assert config.count(b'profile=0')==1 and b'verbose=0' in config and b'd3d9=dxvk' in config
packages=[]
for variant in ('transitions','control','math-control','diagnostic','rollback'):
    enabled=variant not in ('control','rollback')
    floatmath=variant not in ('math-control','rollback')
    sampling=variant=='diagnostic'
    files={
        prefix+'profile.txt':b'1\n' if sampling else b'0\n',
        prefix+'perf23-balance.txt':b'1\n' if enabled else b'0\n',
        prefix+'no-balance.txt':b'0\n',
        prefix+'perf22-floatmath.txt':b'1\n' if floatmath else b'0\n',
        prefix+'perf21-fastmath.txt':b'1\n',
        prefix+'perf20-fusion.txt':b'1\n',prefix+'perf19-matrix.txt':b'1\n',
        prefix+'perf17-hotblocks.txt':b'0\n',prefix+'perf17-capture.txt':b'1\n',
        prefix+'perf18-roundguard.txt':b'0\n',prefix+'perf8-turbo.txt':b'0\n',
        prefix+'drive_c/PES13/pes2013.box64.txt':boxconfig,
        prefix+'drive_c/PES13/pes2013.wine-nx.txt':config.replace(b'profile=0',b'profile=1') if sampling else config,
        'PERF23.md':(p/'docs/PERF23.md').read_bytes(),
        'PERF22-RESULT.md':(p/'docs/PERF22-RESULT.md').read_bytes(),
    }
    if variant in ('transitions','rollback'):
        files.update({prefix+'pes13-nx.nro':old if variant=='rollback' else nro,
            prefix+'drive_c/windows/system32/winebox64.dll':dll,
            prefix+'drive_c/PES13/d3d9.dll':dxvk,
            'licenses/DXVK-LICENSE.txt':(p/'licenses/DXVK-LICENSE.txt').read_bytes()})
    assert not any(n.endswith(('.exe','settings.dat','ntdll.dll','.log')) for n in files)
    assert sum(n.endswith('.nro') for n in files)==int(variant in ('transitions','rollback'))
    files['PERF23-manifest.json']=json.dumps({
        'variant':variant,'abi':4,'hardware_tested':variant=='rollback',
        'requires':'Existing working PES13 installation; flag overlays require PERF23 NRO',
        'secondary_balancing':enabled,'log_history':0 if variant=='rollback' else 4,
        'continuous_sampling':sampling,'sampling_interval_ms':10 if sampling else None,
        'per_block_X87DOUBLE':0 if floatmath else 1,'baseline_X87DOUBLE':1,
        'per_block_FASTROUND':1,'baseline_FASTROUND':0,'SAFEFLAGS':2,
        'math_scope':'PERF21/22 unchanged, first successful present, main text excluding matrix page',
        'retains_PERF19':True,'retains_PERF20':True,'retains_PERF21':True,
        'preserves':['game data','saves','settings.dat','controllers','ntdll'],
        'nro':meta if variant=='transitions' else None,
        'files':{name:sha(blob) for name,blob in files.items()},
    },indent=2).encode()
    target=p/'dist'/f'pes13-perf23-{variant}.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for name,blob in files.items(): z.writestr(name,blob)
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None and set(z.namelist())==set(files)
        assert all(z.read(name)==blob for name,blob in files.items())
    packages.append({'path':str(target),'bytes':target.stat().st_size,'sha256':sha(target.read_bytes())})
(w/'packages.json').write_text(json.dumps(packages,indent=2)+'\n')
print(json.dumps(packages,indent=2))
