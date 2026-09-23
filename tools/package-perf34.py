"""Package PERF34 with one configuration.ini and no boolean sidecar files."""
from pathlib import Path
import hashlib,io,json,zipfile
from nro_assets import inspect_nro

p=Path(__file__).resolve().parents[1];w=p/'local/perf34';prefix='switch/pes13-nx/'
sha=lambda b:hashlib.sha256(b).hexdigest()
CONFIG = (p/'config/configuration.ini').read_bytes()

def main():
    status=json.loads((w/'build-status.json').read_text())
    assert status=={'state':'complete','restored':True},status
    verify=json.loads((w/'verification.json').read_text())
    assert verify.get('unified_configuration') is True
    for name,digest in verify['changed_sources_sha256'].items():
        assert sha((p/name).read_bytes())==digest,name
    prior=p/'dist/pes13-perf32-game-blocks.zip'
    with zipfile.ZipFile(prior) as z:
        assert z.testzip() is None
        manifest=json.loads(z.read('PERF32-manifest.json'))
        baseline={name:z.read(name) for name in z.namelist() if name.startswith(prefix)}
        assert all(sha(data)==manifest['files'][name] for name,data in baseline.items())
    nro=(w/'payload'/prefix/'pes13-nx.nro').read_bytes()
    assert sha(nro)==json.loads((w/'build.json').read_text())['nro_sha256']
    assert b'pes13-nx-0.2.0-perf34-config' in nro
    meta=inspect_nro(nro,(p/'assets/icon.jpg').read_bytes(),expected_title='PES13-NX PERF34 CONFIG')
    # Only root-level boolean controls are migrated.  Game-specific Wine and
    # Box64 text remain untouched because they are structured settings, not
    # boolean switches.
    old_flags={n for n in baseline if n.startswith(prefix) and n.count('/')==2 and n.endswith('.txt')}
    data={n:v for n,v in baseline.items() if n not in old_flags}
    data[prefix+'pes13-nx.nro']=nro
    data[prefix+'configuration.ini']=CONFIG
    assert not any(n.startswith(prefix) and n.count('/')==2 and n.endswith('.txt') for n in data)
    variants={
        'config':data,
        'control':dict(data,**{prefix+'configuration.ini':CONFIG.replace(b'perf33_blocks=1',b'perf33_blocks=0')}),
        'diagnostics':dict(data,**{prefix+'configuration.ini':CONFIG.replace(b'profile=0',b'profile=1')}),
    }
    reports=[]
    for variant,payload in variants.items():
        assert sum(n.endswith('.nro') for n in payload)==1
        assert not any(n.lower().endswith(('.exe','.dat','.reg','.log','ntdll.dll')) for n in payload)
        assert all('/users/' not in n for n in payload)
        files=dict(payload)
        for name in ('PERF34.md','PERF34-RESULT.md','PERF33.md','PERF32-RESULT.md'):
            files[name]=(p/'docs'/name).read_bytes()
        for name in ('THIRD_PARTY.md','LICENSE'):
            files[name]=(p/name).read_bytes()
        files.update({f.relative_to(p).as_posix():f.read_bytes() for f in (p/'licenses').rglob('*') if f.is_file()})
        files['PERF34-manifest.json']=(json.dumps(dict(variant=variant,base='PERF33 FASTMATH',
            abi=4,nro_metadata=meta,nro_sha256=sha(nro),target_match_fps=30,target_verified=False,
            hardware_tested=False,unified_configuration=True,
            legacy_boolean_sidecars='runtime fallback only; not shipped',
            files={n:sha(v) for n,v in files.items()}),indent=2)+'\n').encode()
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
            for name,value in sorted(files.items()):
                assert not name.startswith('/') and '..' not in Path(name).parts
                entry=zipfile.ZipInfo(name,(2026,9,23,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED
                z.writestr(entry,value)
        raw=buffer.getvalue()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            assert z.testzip() is None and all(z.read(n)==v for n,v in files.items())
        target=p/'dist'/f'pes13-perf34-{variant}.zip'
        if target.exists():
            assert target.read_bytes()==raw,('Refusing to overwrite changed package',target)
        else:
            with target.open('xb') as f:f.write(raw)
        reports.append(dict(path=str(target),bytes=len(raw),sha256=sha(raw),variant=variant,
                            complete_nro=True,zip_integrity=True,hardware_tested=False,
                            unified_configuration=True,boolean_sidecars_shipped=False))
    (w/'packages.json').write_text(json.dumps(reports,indent=2)+'\n')
    print(json.dumps(reports,indent=2))

if __name__=='__main__':main()
