"""Differential bounds tests of actual before/after FEX DecodeLoop source."""
import argparse, hashlib, json, os, subprocess
from pathlib import Path
from fex_protect_roundtrip import function

ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); a.output.parent.mkdir(parents=True,exist_ok=True)
    reports={}; hashes={}
    for label in ('before','source'):
        path=a.work/label/'FEXCore/Source/Interface/Core/Frontend.cpp'
        data=path.read_text(); hashes[label]=sha(path)
        loop=function(data,'void Decoder::DecodeLoop(')
        begin=data.index('  // The decoder already stops') if label=='source' else data.index('  DecodedBuffer = PoolObject.ReownOrClaimBuffer();')
        end=data.index('\n',data.index('DecodedBuffer = PoolObject.ReownOrClaimBuffer(',begin))
        capacity=data[begin:end]
        template=ROOT/'tests/fex_decoder_capacity.cpp'
        generated=a.output.parent/(label+'-capacity.cpp')
        generated.write_text(template.read_text().replace('// INSERT_REAL_LOOP_HERE',loop)
                             .replace('// INSERT_REAL_CAPACITY_HERE',capacity))
        exe=a.output.parent/(label+'-capacity')
        subprocess.run(['g++','-std=c++20','-O1','-g','-Wall','-Wextra','-Werror',
            '-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-fno-pie','-no-pie',
            '-I'+str(a.work/'adapter'),str(generated),'-o',str(exe)],check=True)
        result=subprocess.check_output([str(exe)],text=True,timeout=60)
        (a.output.parent/(label+'-capacity.txt')).write_text(result)
        rows=[list(map(int,line.split())) for line in result.splitlines()]
        assert len(rows)==384
        reports[label]=rows
    for old,new in zip(reports['before'],reports['source']):
        assert old[:4]==new[:4] and old[5:]==new[5:],(old,new)
        assert new[4]<=old[4] and new[5]*128<new[4]
    samples={str(limit):next(r[4] for r in reports['source'] if r[:3]==[limit,0,0])
             for limit in (0,1,128,500,5000,65536,2**64-1)}
    report=dict(passed=True,hardware_tested=False,source_hashes=hashes,
        test_sources={str(n.relative_to(ROOT)):sha(n) for n in (Path(__file__),template)},
        adapter_sha256=sha(a.work/'adapter/horizon_decode_set.h'),cases=384,
        all_decode_traces_equal=True,asan_ubsan=True,baseline_bytes=8388608,requested_bytes=samples,
        scope='Actual DecodeLoop and allocation expression; mocked instruction decode and context, real bounded worklists and ASan scratch buffers.',
        checks=['Instruction caps 0/1/128/500/5000/65536 and uint64 maximum',
            'Sequential, multiblock, invalid entry/nonentry, overlapping and bad-relocation paths',
            'Pause/resume after 1, 7 or 63 guest bytes and unpaused decode',
            'Decoded PCs, block contents, counts and bounds equal before/after'])
    a.output.write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps(report))

if __name__=='__main__':main()
