"""Extract bounded FAULT28 runtime code from a local log, without executing it."""
from pathlib import Path
import argparse, hashlib, json, re
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

def decode(source, output):
    source=Path(source); output=Path(output); output.mkdir(parents=True,exist_ok=True)
    chunks={}; records=[]; summary=[]
    pattern=re.compile(r'^\[FAULT28\] (caller|lookup|stack|object) at=([0-9a-f]{8}) hex=([0-9a-f]{2,64})$')
    with source.open(errors='replace') as stream:
        for raw in stream:
            line=raw.rstrip('\r\n')
            if not line.startswith('[FAULT28]'): continue
            assert len(line)<=256, 'Oversized diagnostic line'
            match=pattern.fullmatch(line)
            if match:
                kind, address, data=match.groups(); at=int(address,16); data=bytes.fromhex(data)
                part=chunks.setdefault(kind,{})
                assert at not in part, 'Multiple captures in one log: split by run first'
                part[at]=data
                assert sum(map(len,part.values()))<=1024, 'Oversized diagnostic segment'
            elif ' record index=' in line:
                records.append(line); assert len(records)<=40
            else:
                summary.append(line); assert len(summary)<=100
    manifest={'log_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'summary':summary,
              'record_samples':records,'segments':{},'limits':'Inferred layout; capture can race game writes.'}
    for kind, parts in chunks.items():
        start=min(parts); end=max(a+len(b) for a,b in parts.items()); blob=bytearray()
        for at, data in sorted(parts.items()):
            assert at==start+len(blob), 'Noncontiguous capture; do not fill gaps with fabricated bytes'
            blob.extend(data)
        name=f'{kind}-{start:08x}'; (output/(name+'.bin')).write_bytes(blob)
        if kind in ('caller','lookup'):
            cs=Cs(CS_ARCH_X86,CS_MODE_32)
            # The caller dump starts before our established instruction boundary.
            skip=0x28 if kind=='caller' and start==0x115c300 else 0
            instructions=list(cs.disasm(bytes(blob[skip:]),start+skip))
            (output/(name+'.txt')).write_text('\n'.join(
                f'{i.address:08x}  {i.bytes.hex():24s} {i.mnemonic} {i.op_str}' for i in instructions)+'\n')
        manifest['segments'][kind]={'start':start,'end':end,'bytes':len(blob),
            'sha256':hashlib.sha256(blob).hexdigest()}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log'); parser.add_argument('output')
    args=parser.parse_args(); decode(args.log,args.output)
