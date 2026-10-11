"""Inspect installed metadata from the actual plaintext-section NSP artifact."""
import argparse,hashlib,importlib.util,json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))

def inspect_forwarder(blob,report):
    spec=importlib.util.spec_from_file_location('forwarder_checks',ROOT/'tools/build-fextendo-forwarder.py')
    check=importlib.util.module_from_spec(spec);spec.loader.exec_module(check)
    assert hashlib.sha256(blob).hexdigest()==report['forwarder']['sha256']
    ncas=check.pfs_files(blob);metadata=[];exefs=[]
    for name,data in ncas.items():
        assert name.split('.')[0]==hashlib.sha256(data).hexdigest()[:32]
        at=0
        while (at:=data.find(b'PFS0',at))>=0:
            try:files=check.pfs_files(data[at:])
            except (AssertionError,ValueError,struct.error,UnicodeError):files={}
            metadata.extend(v for n,v in files.items() if n.endswith('.cnmt'))
            if 'main.npdm' in files:exefs.append(files)
            at+=4
    assert len(metadata)==1
    meta=metadata[0];tid,version=struct.unpack_from('<QI',meta)
    assert tid==0x052d1913f51f5000 and version==0x20000 and meta[12]==0x80
    assert len(exefs)==1 and 'fxtmem' not in exefs[0]
    from fextendo_low_window import automatic_descriptor
    assert exefs[0]['fxtauto']==automatic_descriptor()
    spec=importlib.util.spec_from_file_location('npdm_checks',ROOT/'tools/build-as39-probe.py')
    npdm=importlib.util.module_from_spec(spec);spec.loader.exec_module(npdm)
    npdm.check_npdm(exefs[0]['main.npdm'],32,tid)
    assert struct.unpack_from('<I',exefs[0]['main.npdm'],0x14)[0]==0
    assert report['automatic'] and report['forwarder']['marker']=='fxtauto-v1'
    ext,count=struct.unpack_from('<HH',meta,14);controls=[]
    for i in range(count):
        rec=meta[32+ext+i*56:32+ext+(i+1)*56]
        data=ncas[rec[32:48].hex()+'.nca']
        assert hashlib.sha256(data).digest()==rec[:32]
        assert len(data)==int.from_bytes(rec[48:54],'little')
        if rec[54]==3:controls.append(data)
    assert len(controls)==1
    control=controls[0];start=control.index(b'PES13-FEXTendo\0')
    titles=[control[start+i*0x300:start+i*0x300+0x200].split(b'\0')[0].decode() for i in range(16)]
    assert titles==['PES13-FEXTendo']*16
    display=control[start+0x3060:start+0x3070].split(b'\0')[0].decode()
    assert display=='0.4.1'
    assert report['target']=='/switch/pes13-fex/pes13-fex.nro'
    assert any(report['target'].encode() in data for data in ncas.values())
    result=dict(passed=True,hardware_tested=False,nsp_sha256=hashlib.sha256(blob).hexdigest(),
        title_id=f'{tid:016x}',cnmt_version=version,nacp_version=display,titles=titles,
        target=report['target'],cnmt_content_hashes_checked=True,
        default_address_space='32-bit no-alias',optional_extension='fxtauto-v1',
        limitations='Verifies package metadata, not the installed Switch HOME cache.')
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('package',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();report=json.loads((a.package/'forwarder-build.json').read_text())
    result=inspect_forwarder((a.package/'forwarders'/report['forwarder']['nsp']).read_bytes(),report)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS: actual NSP title, 16 languages, CNMT 131072, content hashes, canonical target, stock 32-bit no-alias NPDM with fxtauto-v1')
if __name__=='__main__':main()
