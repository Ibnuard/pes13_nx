"""Package scoped FASTROUND, same-NRO control, diagnostic and exact PERF20 rollback."""
from pathlib import Path
import hashlib,json,zipfile
from nro_assets import inspect_nro

p=Path(__file__).resolve().parents[1]; w=p/'local/perf21'; prefix='switch/pes13-nx/'
sha=lambda b:hashlib.sha256(b).hexdigest()
build=json.loads((w/'build.json').read_text()); assert build['source_restored']
emit=json.loads((w/'build-emitter-verification.json').read_text())
assert len(emit['files'])==13 and emit['passes_per_file']==4 and emit['only_macro_changes']
assert (w/'worker-c-fused.bin').read_bytes()==(p/'local/perf20/worker-fused.bin').read_bytes()
nro=(w/'payload'/prefix/'pes13-nx.nro').read_bytes()
assert sha(nro)==build['nro_sha256'] and b'pes13-nx-0.2.0-perf21-fastmath' in nro
assert all(tag in nro for tag in (b'[PERF19]',b'[PERF20]',b'[PERF21]'))
meta=inspect_nro(nro,(p/'assets/icon.jpg').read_bytes(),expected_title='PES13-NX PERF21')
old=(p/'local/perf20/payload'/prefix/'pes13-nx.nro').read_bytes()
assert sha(old)=='529e68301c30de854c13cb51280acc8bfadc80eafe98fa2bf44666255fa36a72'
prior=p/'dist/pes13-perf20-roundfusion.zip'
assert sha(prior.read_bytes())=='ec4573fccfe8dd26c325cb3eb4f3c5a8e722ea793110210d7067dfe8f516485c'
with zipfile.ZipFile(prior) as z:
    manifest=json.loads(z.read('PERF20-manifest.json'))
    dll=z.read(prefix+'drive_c/windows/system32/winebox64.dll')
    dxvk=z.read(prefix+'drive_c/PES13/d3d9.dll')
    assert z.read(prefix+'pes13-nx.nro')==old
assert sha(dll)==manifest['files'][prefix+'drive_c/windows/system32/winebox64.dll']=='42463d635af0874c301317c481eeb401d42963ef4d119059b3e309bb14f7a46b'
assert sha(dxvk)==manifest['files'][prefix+'drive_c/PES13/d3d9.dll']
config=(p/'config/drive_c/PES13/pes2013.wine-nx.txt').read_bytes()
boxconfig=(p/'config/drive_c/PES13/pes2013.box64.txt').read_bytes()
settings=dict(line.split('=',1) for line in boxconfig.decode().splitlines() if line.startswith('BOX64_'))
assert settings=={'BOX64_DYNAREC_'+k:str(v) for k,v in {'SAFEFLAGS':2,'FASTNAN':0,'FASTROUND':0,'X87DOUBLE':1,'BIGBLOCK':0,'STRONGMEM':1,'CALLRET':0}.items()}
assert config.count(b'profile=0')==1 and b'verbose=0' in config and b'd3d9=dxvk' in config
packages=[]
for variant in ('fastmath','control','rollback','diagnostic'):
    enabled=variant in ('fastmath','diagnostic'); sampling=variant=='diagnostic'
    files={
        prefix+'profile.txt':b'1\n' if sampling else b'0\n',
        prefix+'perf21-fastmath.txt':b'1\n' if enabled else b'0\n',
        prefix+'perf20-fusion.txt':b'1\n',prefix+'perf19-matrix.txt':b'1\n',
        prefix+'perf17-hotblocks.txt':b'0\n',prefix+'perf17-capture.txt':b'1\n',
        prefix+'perf18-roundguard.txt':b'0\n',prefix+'perf8-turbo.txt':b'0\n',
        prefix+'drive_c/PES13/pes2013.box64.txt':boxconfig,
        prefix+'drive_c/PES13/pes2013.wine-nx.txt':config.replace(b'profile=0',b'profile=1') if sampling else config,
        'PERF21.md':(p/'docs/PERF21.md').read_bytes(),
        'PERF20-RESULT.md':(p/'docs/PERF20-RESULT.md').read_bytes(),
    }
    if variant in ('fastmath','rollback'):
        files.update({prefix+'pes13-nx.nro':old if variant=='rollback' else nro,
            prefix+'drive_c/windows/system32/winebox64.dll':dll,
            prefix+'drive_c/PES13/d3d9.dll':dxvk,
            'licenses/DXVK-LICENSE.txt':(p/'licenses/DXVK-LICENSE.txt').read_bytes()})
    assert not any(n.endswith(('.exe','settings.dat','ntdll.dll')) for n in files)
    assert sum(n.endswith('.nro') for n in files)==int(variant in ('fastmath','rollback'))
    files['PERF21-manifest.json']=json.dumps({
        'variant':variant,'abi':4,'hardware_tested':False,
        'requires':'Existing working PES13 installation; control/diagnostic overlays require PERF21 NRO',
        'continuous_sampling':sampling,'sampling_interval_ms':10 if sampling else None,
        'per_block_FASTROUND':int(enabled),'baseline_FASTROUND':0,'SAFEFLAGS':2,
        'gate':'first successful Vulkan present','scope':'full main .text pages except PERF19 matrix page',
        'retains_PERF19':True,'retains_PERF20':True,
        'preserves':['game data','saves','settings.dat','controllers','ntdll'],
        'nro':meta if variant=='fastmath' else None,
        'files':{name:sha(blob) for name,blob in files.items()},
    },indent=2).encode()
    target=p/'dist'/f'pes13-perf21-{variant}.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for name,blob in files.items():z.writestr(name,blob)
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None and set(z.namelist())==set(files)
        assert all(z.read(name)==blob for name,blob in files.items())
    packages.append({'path':str(target),'bytes':target.stat().st_size,'sha256':sha(target.read_bytes())})
(w/'packages.json').write_text(json.dumps(packages,indent=2)+'\n')
print(json.dumps(packages,indent=2))
