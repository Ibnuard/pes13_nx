"""Build one full diagnostic overlay with an unchanged PERF36 execution preset."""
from pathlib import Path
import hashlib,io,json
from zipfile import ZipFile,ZipInfo,ZIP_DEFLATED
p=Path(__file__).resolve().parents[1];w=p/'local/perf37';prefix='switch/pes13-nx/'
sha=lambda b:hashlib.sha256(b).hexdigest()

def main():
    report=json.loads((w/'verification.json').read_text())
    assert report['source_restored'] and report['dispatch_and_native_pass_source_identical']
    assert len(report['emitter_sources_identical_to_perf36'])==14
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
    payload=dict(baseline); changed=[prefix+'pes13-nx.nro']
    payload[changed[0]]=nro
    for suffix in ('configuration.ini','drive_c/PES13/pes2013.wine-nx.txt'):
        name=prefix+suffix
        assert payload[name].count(b'profile=0')==1
        payload[name]=payload[name].replace(b'profile=0',b'profile=1');changed.append(name)
    assert sorted(n for n in payload if payload[n]!=baseline[n])==sorted(changed)
    assert sum(n.endswith('.nro') for n in payload)==1
    assert not any('/users/' in n or n.lower().endswith(('.exe','.reg','.dat','.log')) for n in payload)
    files=dict(credits,**payload)
    for name in ('PERF36-RESULT.md','PERF37.md'):
        files[name]=(p/'docs'/name).read_bytes()
    manifest=dict(variant='PERF37 JIT probe',base='PERF36 scoped-fastnan',abi=old['abi'],
        nro_metadata=report['nro_metadata'],nro_sha256=sha(nro),
        dxvk=old['dxvk'],changed_runtime_files=changed,performance_improvement_claimed=False,
        execution_policy_unchanged=True,target_match_fps=30,target_verified=False,hardware_tested=False,
        files={n:sha(b) for n,b in sorted(files.items())})
    files['PERF37-manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    buf=io.BytesIO()
    with ZipFile(buf,'w',ZIP_DEFLATED) as z:
        for n,b in sorted(files.items()):
            assert not n.startswith('/') and '..' not in Path(n).parts
            info=ZipInfo(n,(2026,9,23,0,0,0));info.compress_type=ZIP_DEFLATED;z.writestr(info,b)
    raw=buf.getvalue(); target=p/'dist/pes13-perf37-jit-probe.zip'
    if target.exists(): assert target.read_bytes()==raw,'Refusing to overwrite a changed package'
    else:
        with target.open('xb') as f:f.write(raw)
    with ZipFile(target) as z:
        assert z.testzip() is None and all(z.read(n)==b for n,b in files.items())
    result=dict(path=str(target),sha256=sha(raw),bytes=len(raw),nro_sha256=sha(nro),
        changed_runtime_files=changed,hardware_tested=False,performance_improvement_claimed=False)
    (w/'packages.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
