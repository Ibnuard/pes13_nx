"""Build actual before/after allocator and storage bodies under ASan/UBSan."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def function(s, signature):
    pos=s.index(signature); start=s.index('{',pos); end=start+1;depth=1
    while depth:
        depth+=(s[end]=='{')-(s[end]=='}');end+=1
    return s[pos:end]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('before','candidate','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);records={}
    for label,src in [('baseline',a.before),('candidate',a.candidate)]:
        out=a.output/label;out.mkdir(exist_ok=True)
        memory=(src/'src/dxvk/dxvk_memory.cpp').read_text()
        pool=function((src/'src/dxvk/dxvk_memory.h').read_text(),'  struct DxvkMemoryPool {')+';'
        chunk=function(memory,'  bool DxvkMemoryAllocator::allocateChunkInPool(')
        image=function((src/'src/dxvk/dxvk_image.cpp').read_text(),
                       '  Rc<DxvkResourceAllocation> DxvkImage::assignStorageWithUsage(')
        buffer=function((src/'src/dxvk/dxvk_buffer.h').read_text(),
                        '    Rc<DxvkResourceAllocation> assignStorage(Rc<DxvkResourceAllocation>&& slice)')
        header=(src/'src/dxvk/dxvk_allocator.h').read_text().replace('#include "../util/util_env.h"',
            '#include "'+str(src/'src/util/util_bit.h')+'"\nnamespace dxvk::env { constexpr bool is32BitHostPlatform() { return true; } }')
        (out/'dxvk_allocator.h').write_text(header)
        (out/'dxvk_allocator.cpp').write_text((src/'src/dxvk/dxvk_allocator.cpp').read_text().replace('../util/',str(src/'src/util')+'/'))
        results={}
        for test in ('chunks','storage'):
            s=(ROOT/f'tests/dxvk_kit17_{test}.cpp').read_text()
            for key,val in [('POOL',pool),('CHUNK',chunk),('IMAGE',image),('BUFFER',buffer)]:
                s=s.replace('/* ACTUAL_'+key+' */',val)
            code=out/(test+'.cpp');code.write_text(s);exe=out/test
            cmd=[shutil.which('g++'),'-std=c++17','-O1','-g','-fno-pie','-no-pie',
                 '-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(out),
                 '-I'+str(src/'src'),'-I'+str(src/'include/vulkan/include'),str(code)]
            if test=='chunks':cmd+=[str(out/'dxvk_allocator.cpp')]
            if label=='baseline':cmd+=['-DBASELINE=1']
            subprocess.run(cmd+['-o',str(exe)],check=True)
            r=subprocess.run([str(exe)],text=True,capture_output=True)
            (out/(test+'.log')).write_text(r.stdout+r.stderr)
            assert r.returncode==0,(label,test,r.stdout,r.stderr)
            results[test]=r.stdout.strip();print(label+': '+r.stdout,flush=True)
            if label=='baseline' and test=='storage':
                for what in ('image','buffer'):
                    bad=subprocess.run([str(exe),what],text=True,capture_output=True)
                    (out/(what+'-null.log')).write_text(bad.stdout+bad.stderr)
                    assert bad.returncode!=0 and 'null pointer' in bad.stderr,bad
                    results[what+'_null_reproduced']=True
        records[label]=dict(passed=True,results=results,bodies={n:hashlib.sha256(v.encode()).hexdigest()
                           for n,v in [('pool',pool),('chunk',chunk),('image',image),('buffer',buffer)]})
    sources={str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),
            ROOT/'tests/dxvk_kit17_chunks.cpp',ROOT/'tests/dxvk_kit17_storage.cpp')}
    report=dict(passed=True,asan_ubsan=True,pressure_cases=768,records=records,sources=sources,
                limits='Fault-injected Vulkan allocation and resource handles. Real allocator, Rc and storage bodies; no GPU or full game.')
    (a.output/'tests.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
