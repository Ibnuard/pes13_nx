"""Real PE alias reader/claim helper with forced reuse and concurrent readers."""
from pathlib import Path
import argparse, hashlib, json, subprocess, tempfile
ROOT=Path(__file__).resolve().parents[1]
def function(data,name):
    a=data.index(name+'('); a=data.rfind('\n',0,a)+1; b=data.index('{',a); end=b+1; depth=1
    while depth:
        depth+=(data[end]=='{')-(data[end]=='}'); end+=1
    return data[a:end]
def main():
    if not __debug__: raise RuntimeError('Assertions required')
    ap=argparse.ArgumentParser(); ap.add_argument('--output',type=Path,required=True); args=ap.parse_args()
    source=(ROOT/'src/fex/module_host.cpp').read_text()
    declaration=source[source.index('struct CodeAlias {'):source.index('\nbool ClaimAlias(')]
    claim=function(source,'ClaimAlias'); reader=function(source,'CachedAlias')
    prefix=r'''
#include <cstdint>
#include <cassert>
#include <cstdio>
#include <thread>
#include <atomic>
'''+declaration+'\n'+claim+r'''
int inject=0; uintptr_t replacement=0x300000;
void reuse() {
    uintptr_t old=__atomic_load_n(&CodeAliases[0].rx,__ATOMIC_RELAXED);
    assert(ClaimAlias(CodeAliases[0],old));
    __atomic_store_n(&CodeAliases[0].rx,uintptr_t(0),__ATOMIC_RELAXED);
    __atomic_fetch_add(&CodeAliases[0].sequence,1,__ATOMIC_RELEASE);
    assert(ClaimAlias(CodeAliases[0],0));
    __atomic_store_n(&CodeAliases[0].rx,replacement,__ATOMIC_RELAXED);
    __atomic_store_n(&CodeAliases[0].rw,uintptr_t(0x400000),__ATOMIC_RELAXED);
    __atomic_store_n(&CodeAliases[0].size,uint64_t(0x20000),__ATOMIC_RELAXED);
    __atomic_fetch_add(&CodeAliases[0].sequence,1,__ATOMIC_RELEASE);
}
template<class T> T load(const T* ptr,int order) {
    const T value=__atomic_load_n(ptr,order);
    const void* addresses[]={&CodeAliases[0].rx,&CodeAliases[0].size,&CodeAliases[0].rw};
    if(inject && static_cast<const void*>(ptr)==addresses[inject-1]) { inject=0; reuse(); }
    return value;
}
#define __atomic_load_n load
'''
    tail=r'''
#undef __atomic_load_n
void reset() {
    for(auto& x:CodeAliases) x={};
    CodeAliases[0]={0x100000,0x200000,0x1000,0};
    CodeAliases[1]={0x110000,0x500000,0x1000,0};
}
int main() {
    for(unsigned step=1;step<=3;step++) {
        reset(); inject=step; void* result=nullptr;
        assert(CachedAlias(reinterpret_cast<void*>(0x110020),4,&result)==1);
        assert(uintptr_t(result)==0x500020);
    }
    // Same-RX reuse (ABA) changes RW while owner of target B stays alive.
    reset(); replacement=0x100000; inject=1; void* result=nullptr;
    // This artificial new A range overlaps B, so test a stable address outside
    // its range; reader must skip the torn A snapshot and find B in its slot.
    CodeAliases[1]={0x500000,0x600000,0x1000,0};
    assert(CachedAlias(reinterpret_cast<void*>(0x500020),4,&result)==1 && uintptr_t(result)==0x600020);
    reset(); replacement=0x300000;
    auto read=[] { for(unsigned i=0;i<100000;i++) {
        void* result=nullptr;
        assert(CachedAlias(reinterpret_cast<void*>(0x110020),4,&result)==1);
        assert(uintptr_t(result)==0x500020);
    }};
    std::thread a(read),b(read),c(read);
    for(unsigned i=0;i<100000;i++) reuse();
    a.join();b.join();c.join();
    assert(CachedAlias(reinterpret_cast<void*>(UINTPTR_MAX-1),4,&result)==-1);
    assert(CachedAlias(reinterpret_cast<void*>(0x110fff),2,&result)==-1);
    puts("PASS forced metadata interleavings, reuse, 300000 concurrent lookups, overflow/boundaries");
}
'''
    with tempfile.TemporaryDirectory(prefix='fex-alias-') as folder:
        cpp=Path(folder)/'test.cpp'; binary=Path(folder)/'test'; cpp.write_text(prefix+reader+tail)
        cmd=['clang++','-std=c++17','-O1','-g','-pthread','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(cpp),'-o',str(binary)]
        subprocess.run(cmd,check=True)
        result=subprocess.run([str(binary)],capture_output=True,text=True,check=True,timeout=60)
        # Ensure the forced race really detects loss of snapshot validation.
        guard='__atomic_load_n(&entry.sequence, __ATOMIC_ACQUIRE) != sequence || '
        assert reader.count(guard)==1
        cpp.write_text(prefix+reader.replace(guard,'')+tail)
        subprocess.run(cmd,check=True)
        mutant=subprocess.run([str(binary)],capture_output=True,text=True,timeout=60)
        if mutant.returncode==0 or 'Assertion failed' not in mutant.stderr:
            raise RuntimeError('Missing generation check was not detected')
    report={'passed':True,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'stdout':result.stdout,'stderr':result.stderr,
            'mutation_without_generation_check_rejected': True,
            'scope':'Actual source helper with deterministic scheduling seam and host threads, ASan/UBSan; not Switch execution'}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n');print(result.stdout)
if __name__=='__main__': main()
