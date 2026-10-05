"""Reproduce r3 private-heap failure and exercise real r4 ARM64 callbacks.

Allocator/OS failure causes are models, not a diagnosis of why the console's
page fallback failed; the delivered 10-MiB request and pointer contract are real.
"""
import argparse,hashlib,json,struct
from pathlib import Path
from fextendo_fragmented_heap_binary import Model,MIB,PAGE
def main():
    ap=argparse.ArgumentParser();ap.add_argument('elf',type=Path);ap.add_argument('--before',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    regressions=[]
    for path in (a.before,a.elf):
        for failure in ('source','virtual_range','map','budget'):
            m=Model(path);m.host();m.limit=16*MIB;old=m.heap(5*MIB,16);assert old
            m.vm.mem_write(old,b'OLD');m.vm.mem_write(old+5*MIB-1,b'Z')
            held=[m.allocate(16*MIB),m.allocate(8*MIB)];assert all(held)
            aliases=[]
            if failure=='budget':
                m.limit=65536
                for _ in range(8):aliases.append(m.call('pes13_cpu_pages_allocate',16*MIB,4096))
                assert all(aliases) and m.stats()[3]==128*MIB
            m.limit=0 if failure=='source' else 65536
            m.no_va=failure=='virtual_range'
            if failure=='map':m.fail_map=m.map_calls+2
            new=m.heap(10*MIB,16)
            assert bool(new)==(path==a.elf),(str(path),failure,new)
            assert bytes(m.vm.mem_read(old,3))==b'OLD' and bytes(m.vm.mem_read(old+5*MIB-1,1))==b'Z'
            if new:
                raw,n=struct.unpack('<QQ',m.vm.mem_read(new-16,16));assert n==10*MIB
                assert raw<=new-16 and new%16==0
                m.check_bytes(new,10*MIB);m.heap_free(new)
            m.heap_free(old)
            for p in aliases:m.release(p)
            for p in held:m.release(p)
            m.clean()
            regressions.append({'baseline':path==a.before,'modeled_failure':failure,'request_bytes':10*MIB,'recovered':bool(new)})
        print(('Baseline' if path==a.before else 'Candidate')+' 10-MiB growth cases passed',flush=True)
    m=Model(a.elf);m.host();m.limit=0
    for n,align in ((1,16),(123,64),(PAGE+1,PAGE),(10*MIB,16),(3*MIB+123,65536),(17*MIB,2*MIB)):
        p=m.heap(n,align);assert p and p%align==0;m.check_bytes(p,n);m.heap_free(p)
    # Independent failed paths do not turn spare fragmented reserve pages into
    # a falsely contiguous range; a full pool must still fail without damage.
    full=[m.allocate(8*MIB) for _ in range(8)];assert all(full)
    assert not m.heap(10*MIB,16)
    for i in (0,2,4,6):m.release(full[i])
    assert not m.heap(10*MIB,16)
    m.release(full[1]);p=m.heap(10*MIB,16);assert p;m.check_bytes(p,10*MIB);m.heap_free(p)
    for i in (3,5,7):m.release(full[i])
    m.clean()
    report={'passed':True,'hardware_tested':False,'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
        'baseline_elf_sha256':hashlib.sha256(a.before.read_bytes()).hexdigest(),'regressions':regressions,
        'checks':['Actual callbacks reproduce r3 failure and recover r4 5-to-10 MiB growth with spare reserve',
            'Separate modeled source, VA, map and shared-budget failures; no console cause is assumed',
            'Arbitrary sizes, alignment/header contract, concurrent live compiler owners and complete release',
            'True exhaustion/noncontiguous holes fail while live data remains intact'],
        'sources':{n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in ('tests/fextendo_heap_pressure_binary.py','tests/fextendo_fragmented_heap_binary.py','tests/fextendo_scratch_pages_binary.py')}}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
