"""Full one-NRO candidate, control and diagnostic packages; never settings-only."""
from pathlib import Path
import hashlib,io,json,zipfile
from nro_assets import inspect_nro
p=Path(__file__).resolve().parents[1];w=p/'local/perf32';prefix='switch/pes13-nx/'
sha=lambda b:hashlib.sha256(b).hexdigest()

def main():
    status=json.loads((w/'build-status.json').read_text())
    assert status=={'state':'complete','restored':True}
    verify=json.loads((w/'verification.json').read_text())
    for key in ('same_math_and_copy_emitters_as_perf25','compiled_scoped_block_policy_and_copy_hooks',
                'stock_mesa_link_verified','vendor_clean_at_pinned_revision','source_restored'):
        assert verify[key],key
    assert len(verify['retained_components_identical_objects'])>=4
    for name,digest in verify['changed_sources_sha256'].items():assert sha((p/name).read_bytes())==digest,name
    prior=p/'dist/pes13-perf31-reference-perf25.zip'
    assert sha(prior.read_bytes())=='71df1f6cc34f6f704aa3f5b1453a9db557b9aecc98f34450b5c19ee04f74b222'
    with zipfile.ZipFile(prior) as z:
        assert z.testzip() is None
        manifest=json.loads(z.read('PERF31-manifest.json'))
        baseline={name:z.read(name) for name in z.namelist() if name.startswith(prefix)}
        assert all(sha(data)==manifest['files'][name] for name,data in baseline.items())
    assert sha(baseline[prefix+'pes13-nx.nro'])=='888c77730685a8cff44edf2f07d3146352dbd29b986413a7b2697b20ce9d2d81'
    nro=(w/'payload'/prefix/'pes13-nx.nro').read_bytes()
    assert sha(nro)==json.loads((w/'build.json').read_text())['nro_sha256']
    assert b'pes13-nx-0.2.0-perf32-game-blocks' in nro
    meta=inspect_nro(nro,(p/'assets/icon.jpg').read_bytes(),expected_title='PES13-NX PERF32')
    cfg=prefix+'drive_c/PES13/pes2013.wine-nx.txt';profile=prefix+'profile.txt';flag=prefix+'perf32-blocks.txt'
    data=dict(baseline);data[prefix+'pes13-nx.nro']=nro;data[flag]=b'1\n'
    assert [n for n in baseline if baseline[n]!=data[n]]==[prefix+'pes13-nx.nro']
    assert data[profile]==b'0\n' and data[cfg].count(b'profile=0')==1
    variants={'game-blocks':data,'control':dict(data,**{flag:b'0\n'}),
              'diagnostics':dict(data,**{profile:b'1\n',cfg:data[cfg].replace(b'profile=0',b'profile=1')})}
    assert {n for n in data if data[n]!=variants['control'][n]}=={flag}
    assert {n for n in data if data[n]!=variants['diagnostics'][n]}=={cfg,profile}
    reports=[]
    for variant,payload in variants.items():
        assert sum(n.endswith('.nro') for n in payload)==1
        assert not any(n.lower().endswith(('.exe','.dat','.reg','.log','ntdll.dll')) for n in payload)
        assert all('/users/' not in n for n in payload)
        files=dict(payload)
        for name in ('PERF32.md','PERF31-RESULT.md'):
            files[name]=(p/'docs'/name).read_bytes()
        for name in ('THIRD_PARTY.md','LICENSE'):
            files[name]=(p/name).read_bytes()
        files.update({f.relative_to(p).as_posix():f.read_bytes() for f in (p/'licenses').rglob('*') if f.is_file()})
        files['PERF32-manifest.json']=(json.dumps(dict(variant=variant,base='PERF25',
            abi=4,nro_metadata=meta,nro_sha256=sha(nro),target_match_fps=30,target_verified=False,
            hardware_tested=False,cpu_sampling=variant=='diagnostics',
            scoped_bigblock=0 if variant=='control' else 3,scoped_callret=0,
            requires='Existing PES13 installation; every variant contains the complete NRO',
            files={n:sha(v) for n,v in files.items()}),indent=2)+'\n').encode()
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
            for name,value in sorted(files.items()):
                assert not name.startswith('/') and '..' not in Path(name).parts
                entry=zipfile.ZipInfo(name,(2026,9,22,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED
                z.writestr(entry,value)
        raw=buffer.getvalue()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            assert z.testzip() is None and len(z.namelist())==len(files)
            assert all(z.read(n)==v for n,v in files.items())
        target=p/'dist'/f'pes13-perf32-{variant}.zip'
        if target.exists():assert target.read_bytes()==raw,('Refusing to overwrite changed package',target)
        else:
            with target.open('xb') as f:f.write(raw)
        reports.append(dict(path=str(target),bytes=len(raw),sha256=sha(raw),variant=variant,
                            complete_nro=True,zip_integrity=True,hardware_tested=False,target_verified=False))
    (w/'packages.json').write_text(json.dumps(reports,indent=2)+'\n')
    print(json.dumps(reports,indent=2))

if __name__=='__main__':main()
