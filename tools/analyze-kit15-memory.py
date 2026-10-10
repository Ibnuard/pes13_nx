"""Extract the allocation-stop chain from the archived Kit15 device run."""
import argparse,hashlib,json,re
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('log',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    data=a.log.read_text(errors='replace')
    # Lines wrap within the console renderer. Preserve events while allowing
    # wrapped key/value fields to be read as a single string.
    lines=data.splitlines(); logical=[]
    for line in lines:
        m=re.match(r'^\[([0-9.]+)\] (.*)',line)
        if m and logical and m[1]==logical[-1][0] and not m[2].startswith('['):
            logical[-1][1]+=m[2]
        elif m:logical.append([m[1],m[2]])
    failures=[{'seconds':float(t),'event':s} for t,s in logical if s.startswith('[FEX3-NHEAP-FAIL]')]
    stop=[{'seconds':float(t),'event':s} for t,s in logical if '[FEX2-HEAP] STOP compiler scratch' in s]
    assert len(failures)==len(stop)==1
    assert 'bytes=8388608' in failures[0]['event'] and 'pages_stage=4' in failures[0]['event']
    assert 'reserve_free=0' in failures[0]['event'] and 'heap_free=40682144' in failures[0]['event']
    backing=[{'seconds':float(t),'event':s} for t,s in logical if '[MEM-FAIL]' in s and 'stage=backing' in s]
    assert backing and any('errno=12' in e['event'] for e in backing)
    assert '[FEX3-JIT-LAUNCH] maxinst=128;' in data
    assert '[EXC] unhandled status=0x80000003; parking thread' in data
    vulkan=[(float(t),s) for t,s in logical if '[WAIT-CALLS] kind=vulkan' in s]
    assert 'enter=32392 return=32392' in vulkan[-1][1]
    r=dict(passed=True,input_sha256=hashlib.sha256(a.log.read_bytes()).hexdigest(),input_bytes=a.log.stat().st_size,
        run='0.3.9-kit15',jit_maxinst=128,scratch_failure=failures[0],compiler_stop=stop[0],backing_failures=backing,
        last_vulkan=dict(seconds=vulkan[-1][0],event=vulkan[-1][1]),
        observed='Backing allocation failures precede the compiler scratch allocation stop and parked thread.',
        limitations=['Free heap is an aggregate, not a guarantee of available aligned backing.',
          'The diagnostic budget does not expose the precise cause of every earlier commit failure.',
          'No device test yet establishes whether decoder savings are sufficient for the whole Kitserver match.'])
    a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))

if __name__=='__main__':main()
