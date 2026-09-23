"""One-NRO quiet test package and an optional configuration-only probe."""
from pathlib import Path
import hashlib,io,json
from zipfile import ZipFile,ZipInfo,ZIP_DEFLATED
p=Path(__file__).resolve().parents[1];w=p/'local/perf38';prefix='switch/pes13-nx/'
sha=lambda b:hashlib.sha256(b).hexdigest()

def archive(target,files):
    buf=io.BytesIO()
    with ZipFile(buf,'w',ZIP_DEFLATED) as z:
        for n,b in sorted(files.items()):
            assert not n.startswith('/') and '..' not in Path(n).parts
            info=ZipInfo(n,(2026,9,23,0,0,0));info.compress_type=ZIP_DEFLATED;z.writestr(info,b)
    raw=buf.getvalue()
    if target.exists(): assert target.read_bytes()==raw,'Refusing to overwrite a changed package'
    else:
        with target.open('xb') as f:f.write(raw)
    with ZipFile(target) as z:
        assert z.testzip() is None and all(z.read(n)==b for n,b in files.items())
    return dict(path=str(target),sha256=sha(raw),bytes=len(raw))

def main():
    report=json.loads((w/'verification.json').read_text())
    assert report['source_restored'] and report['dispatch_and_native_pass_source_identical']
    assert report['wrapper_asan_ubsan']=='PASS'
    assert len(report['pass3_machine_code_identical_to_perf36'])==14
    for name,digest in report['changed_source_sha256'].items():
        assert sha((p/name).read_bytes())==digest,name
    nro=(w/'payload'/prefix/'pes13-nx.nro').read_bytes()
    assert sha(nro)==json.loads((w/'build.json').read_text())['nro_sha256']
    with ZipFile(p/'dist/pes13-perf36-scoped-fastnan.zip') as z:
        assert z.testzip() is None
        old=json.loads(z.read('PERF36-manifest.json'))
        baseline={n:z.read(n) for n in z.namelist() if n.startswith(prefix)}
        assert all(sha(b)==old['files'][n] for n,b in baseline.items())
        credits={n:z.read(n) for n in z.namelist() if n.startswith('licenses/') or n in ('LICENSE','THIRD_PARTY.md')}
    payload=dict(baseline)
    payload[prefix+'pes13-nx.nro']=nro
    config=payload[prefix+'configuration.ini']
    assert config.count(b'perf17_capture=1')==1 and config.count(b'profile=0')==1
    assert b'perf38_region_fusion' not in config
    config=config.replace(b'perf17_capture=1',b'perf17_capture=0')
    config+=b'\n# PERF38: scoped direct-control-flow x87 guard fusion. Set 0 for control.\nperf38_region_fusion=1\n'
    payload[prefix+'configuration.ini']=config
    changed=sorted(n for n in payload if payload[n]!=baseline[n])
    assert changed==[prefix+'configuration.ini',prefix+'pes13-nx.nro']
    assert payload[prefix+'drive_c/PES13/pes2013.wine-nx.txt'].count(b'profile=0')==1
    assert sum(n.endswith('.nro') for n in payload)==1
    assert not any('/users/' in n or n.lower().endswith(('.exe','.reg','.dat','.log')) for n in payload)
    assert sha(payload[prefix+'drive_c/PES13/d3d9.dll'])=='265888c31ca78dffa290c39cb7e50bfb02762590e41927906e46fb32f01497fa'
    files=dict(credits,**payload)
    for name in ('PERF37-RESULT.md','PERF38.md'): files[name]=(p/'docs'/name).read_bytes()
    manifest=dict(variant='PERF38 region fusion',base='PERF36 scoped-fastnan',abi=old['abi'],
        nro_metadata=report['nro_metadata'],nro_sha256=sha(nro),dxvk=old['dxvk'],
        changed_runtime_files=changed,scope='112f000-1131000 excluding 112fb90',
        performance_improvement_claimed=False,hardware_tested=False,target_verified=False,
        target_match_fps=30,files={n:sha(b) for n,b in sorted(files.items())})
    files['PERF38-manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    result=archive(p/'dist/pes13-perf38-region-fusion.zip',files)
    result.update(nro_sha256=sha(nro),changed_runtime_files=changed,hardware_tested=False)
    diagnostic={prefix+'configuration.ini':config.replace(b'profile=0',b'profile=1').replace(b'perf17_capture=0',b'perf17_capture=1'),
        prefix+'drive_c/PES13/pes2013.wine-nx.txt':payload[prefix+'drive_c/PES13/pes2013.wine-nx.txt'].replace(b'profile=0',b'profile=1'),
        'PERF38.md':files['PERF38.md']}
    diagnostic['PERF38-diagnostics-manifest.json']=(json.dumps(dict(
        requires_nro_sha256=sha(nro),contains_nro=False,
        files={n:sha(b) for n,b in sorted(diagnostic.items())}),indent=2)+'\n').encode()
    probe=archive(p/'dist/pes13-perf38-diagnostics-overlay.zip',diagnostic)
    results={'main':result,'optional_diagnostics':probe}
    (w/'packages.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(results,indent=2))

if __name__=='__main__':main()
