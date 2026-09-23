"""One-NRO diagnosis package on math-control, quiet overlay and exact rollback."""
from pathlib import Path
import hashlib,json,zipfile
from nro_assets import inspect_nro
p=Path(__file__).resolve().parents[1]; w=p/'local/perf24'; prefix='switch/pes13-nx/'
sha=lambda b:hashlib.sha256(b).hexdigest()
build=json.loads((w/'build.json').read_text())
verify=json.loads((w/'verification.json').read_text())
assert build['source_restored'] and verify['math_emitters_identical_to_perf23']
assert verify['compiled_vulkan_frame_hooks'] and verify['vendor_clean_at_pinned_revision']
assert verify['frame_scenario_tests'].startswith('PASS')
nro=(w/'payload'/prefix/'pes13-nx.nro').read_bytes()
assert sha(nro)==build['nro_sha256']
assert b'pes13-nx-0.2.0-perf24-diagnostics' in nro
assert all(t in nro for t in (b'[FRAME24]',b'[SAMPLE24]',b'[PERF24]',b'[RUN23]',b'[AFF23]',b'[PERF21]',b'[PERF22]'))
meta=inspect_nro(nro,(p/'assets/icon.jpg').read_bytes(),expected_title='PES13-NX PERF24')
prior=p/'dist/pes13-perf23-transitions.zip'
# Verify the actual established artifact and every imported payload hash.
assert sha(prior.read_bytes())=='4ebdddbcae92e024cbf6fd3b1652d28b09db1ced5f6b591ab61dc1507fe40890'
with zipfile.ZipFile(prior) as z:
    oldmanifest=json.loads(z.read('PERF23-manifest.json'))
    imported={name:z.read(name) for name in (
        prefix+'pes13-nx.nro',prefix+'drive_c/windows/system32/winebox64.dll',
        prefix+'drive_c/PES13/d3d9.dll')}
assert all(sha(data)==oldmanifest['files'][name] for name,data in imported.items())
old=imported[prefix+'pes13-nx.nro']
assert sha(old)=='6b331f011a9f23dcaf5438c3d06046c7a7e1ee4dfa350d678eb7828e8e27fb19'
config=(p/'config/drive_c/PES13/pes2013.wine-nx.txt').read_bytes()
box=(p/'config/drive_c/PES13/pes2013.box64.txt').read_bytes()
settings=dict(line.split('=',1) for line in box.decode().splitlines() if line.startswith('BOX64_'))
assert settings=={'BOX64_DYNAREC_'+k:str(v) for k,v in {'SAFEFLAGS':2,'FASTNAN':0,
    'FASTROUND':0,'X87DOUBLE':1,'BIGBLOCK':0,'STRONGMEM':1,'CALLRET':0}.items()}
assert config.count(b'profile=0')==1 and b'verbose=0' in config and b'd3d9=dxvk' in config
packages=[]; controls={}
for variant in ('diagnostics','quiet','rollback'):
    sampled=variant=='diagnostics'
    files={
        prefix+'profile.txt':b'1\n' if sampled else b'0\n',
        prefix+'production.txt':b'1\n',prefix+'no-balance.txt':b'0\n',
        prefix+'perf23-balance.txt':b'1\n',prefix+'perf22-floatmath.txt':b'0\n',
        prefix+'perf21-fastmath.txt':b'1\n',prefix+'perf20-fusion.txt':b'1\n',
        prefix+'perf19-matrix.txt':b'1\n',prefix+'perf17-hotblocks.txt':b'0\n',
        prefix+'perf17-capture.txt':b'1\n',prefix+'perf18-roundguard.txt':b'0\n',
        prefix+'perf8-turbo.txt':b'0\n',prefix+'drive_c/PES13/pes2013.box64.txt':box,
        prefix+'drive_c/PES13/pes2013.wine-nx.txt':config.replace(b'profile=0',b'profile=1') if sampled else config,
        'PERF24.md':(p/'docs/PERF24.md').read_bytes(),
        'PERF23-MATH-RESULT.md':(p/'docs/PERF23-MATH-RESULT.md').read_bytes(),
    }
    controls[variant]={k:v for k,v in files.items() if k.startswith(prefix)}
    if variant!='quiet':
        files.update(imported)
        files[prefix+'pes13-nx.nro']=old if variant=='rollback' else nro
        files['licenses/DXVK-LICENSE.txt']=(p/'licenses/DXVK-LICENSE.txt').read_bytes()
    assert not any(n.endswith(('.exe','settings.dat','ntdll.dll','.log')) for n in files)
    assert sum(n.endswith('.nro') for n in files)==int(variant!='quiet')
    files['PERF24-manifest.json']=json.dumps({
        'variant':variant,'abi':4,'hardware_tested':variant=='rollback',
        'requires':'Existing PES13 install; quiet overlay requires PERF24 NRO',
        'sampling':{'enabled':sampled,'period_ms':20,'active_s_per_10s':2},
        'math':'scoped FASTROUND=1; X87DOUBLE=1; SAFEFLAGS=2; PERF19/20 retained',
        'frame_metrics':variant!='rollback','log_history':4,'secondary_balancing':True,
        'nro_metadata':meta if variant=='diagnostics' else None,
        'preserves':['saves','settings.dat','game data','controllers','ntdll'],
        'files':{k:sha(v) for k,v in files.items()},
    },indent=2).encode()
    target=p/'dist'/f'pes13-perf24-{variant}.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in files.items(): z.writestr(name,data)
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None and set(z.namelist())==set(files)
        assert all(z.read(n)==d for n,d in files.items())
    packages.append({'path':str(target),'bytes':target.stat().st_size,'sha256':sha(target.read_bytes())})
assert {k for k in controls['diagnostics'] if controls['diagnostics'][k]!=controls['quiet'][k]}=={
    prefix+'profile.txt',prefix+'drive_c/PES13/pes2013.wine-nx.txt'}
assert controls['quiet']==controls['rollback']
(w/'packages.json').write_text(json.dumps(packages,indent=2)+'\n')
print(json.dumps(packages,indent=2))
