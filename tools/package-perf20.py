"""One-NRO PERF20 experiment, same-NRO control, diagnostic and PERF19 rollback."""
from pathlib import Path
import hashlib
import json
import zipfile
from nro_assets import inspect_nro

p=Path(__file__).resolve().parents[1]
work=p/'local/perf20'
prefix='switch/pes13-nx/'
sha=lambda b:hashlib.sha256(b).hexdigest()
checks=json.loads((work/'fusion-tests.json').read_text())
assert checks['whole_block_bit_identical'] and checks['cases']>=7680
assert checks['source_sha256']==sha((p/'src/runtime/pes13_perf20_fuse.h').read_bytes())
assert (work/'worker-c-fused.bin').read_bytes()==(work/'worker-fused.bin').read_bytes()
worker=next(b for b in checks['blocks'] if b['kind']=='worker')
assert sha((work/'worker-c-fused.bin').read_bytes())==worker['sha256']
build=json.loads((work/'build.json').read_text())
assert build['source_restored']
nro=(work/'payload'/prefix/'pes13-nx.nro').read_bytes()
assert sha(nro)==build['nro_sha256']
assert b'pes13-nx-0.2.0-perf20-roundfusion' in nro and b'[PERF20]' in nro
meta=inspect_nro(nro,(p/'assets/icon.jpg').read_bytes(),expected_title='PES13-NX PERF20')
old=(p/'local/perf19/payload'/prefix/'pes13-nx.nro').read_bytes()
assert sha(old)=='2e3847ee6f333cc600c2b37f7ac9ca908cb3effbe74ce7b466bc66654d1662b4'
dll=(p/'local/perf15/payload'/prefix/'drive_c/windows/system32/winebox64.dll').read_bytes()
assert sha(dll)=='42463d635af0874c301317c481eeb401d42963ef4d119059b3e309bb14f7a46b'
restore=p/'dist/pes13-perf19-matrix.zip'
assert sha(restore.read_bytes())=='5309e4d2546aeb45fd42017c2f52b9083a12b7d1af32d223344c31ee7ce37247'
with zipfile.ZipFile(restore) as z:
    reference=json.loads(z.read('PERF19-manifest.json'))
    dxvk=z.read(prefix+'drive_c/PES13/d3d9.dll')
assert sha(dxvk)==reference['files'][prefix+'drive_c/PES13/d3d9.dll']
config=(p/'config/drive_c/PES13/pes2013.wine-nx.txt').read_bytes()
assert config.count(b'profile=0')==1 and b'verbose=0' in config and b'd3d9=dxvk' in config
packages=[]
for variant in ('roundfusion','control','rollback','diagnostic'):
    sampling=variant=='diagnostic'
    fusion=variant in ('roundfusion','diagnostic')
    files={
        prefix+'profile.txt':b'1\n' if sampling else b'0\n',
        prefix+'perf20-fusion.txt':b'1\n' if fusion else b'0\n',
        prefix+'perf19-matrix.txt':b'1\n',
        prefix+'perf17-hotblocks.txt':b'0\n',
        prefix+'perf17-capture.txt':b'0\n' if variant=='rollback' else b'1\n',
        prefix+'perf18-roundguard.txt':b'0\n',
        prefix+'perf8-turbo.txt':b'0\n',
        prefix+'drive_c/PES13/pes2013.wine-nx.txt':config.replace(b'profile=0',b'profile=1') if sampling else config,
        'PERF20.md':(p/'docs/PERF20.md').read_bytes(),
        'PERF19-RESULT.md':(p/'docs/PERF19-RESULT.md').read_bytes(),
    }
    if variant in ('roundfusion','rollback'):
        files.update({prefix+'pes13-nx.nro':old if variant=='rollback' else nro,
                      prefix+'drive_c/windows/system32/winebox64.dll':dll,
                      prefix+'drive_c/PES13/d3d9.dll':dxvk,
                      'licenses/DXVK-LICENSE.txt':(p/'licenses/DXVK-LICENSE.txt').read_bytes()})
    assert not any(n.endswith(('.exe','settings.dat','ntdll.dll','.box64.txt')) for n in files)
    assert sum(n.endswith('.nro') for n in files)==(1 if variant in ('roundfusion','rollback') else 0)
    files['PERF20-manifest.json']=json.dumps({
        'variant':variant,'abi':4,'hardware_tested':False,
        'requires':'Existing working PES13 installation; flag-only overlays require the PERF20 NRO',
        'continuous_sampling':sampling,'sampling_interval_ms':10 if sampling else None,
        'rounding_fusion':fusion,'retains_PERF19':True,'scoped_bigblock':False,
        'replay_cases':checks['cases'],'fusion_source_sha256':checks['source_sha256'],
        'preserves':['game','saves','settings.dat','controllers','ntdll','global Compatible preset'],
        'nro':meta if variant=='roundfusion' else None,
        'files':{n:sha(b) for n,b in files.items()},
    },indent=2).encode()
    target=p/'dist'/f'pes13-perf20-{variant}.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for name,blob in files.items():z.writestr(name,blob)
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None and set(z.namelist())==set(files)
        assert all(z.read(name)==blob for name,blob in files.items())
    packages.append({'path':str(target),'bytes':target.stat().st_size,'sha256':sha(target.read_bytes())})
(work/'packages.json').write_text(json.dumps(packages,indent=2)+'\n')
print(json.dumps(packages,indent=2))
