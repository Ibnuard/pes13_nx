"""Run the exact FEX cold-compile metadata gates, bound to module build evidence."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    a = parser.parse_args()
    source = a.source / 'FEXCore/Source/Interface/Core/Core.cpp'
    code = source.read_text()
    start = code.index('  const std::optional<ExecutableFileSectionInfo> Region =')
    end = code.index('    if (Hit && !DiskCache.IsValidating())', start)
    gate = code[start:end]
    gate = gate.replace('    FEXCORE_PROFILE_ACCUMULATION(Thread, AccumulatedDiskCacheLookupTime);', '') + '  }\n'
    harness = r'''
#include <optional>
#include <cstdint>
#include <cassert>
#include <cstdio>
struct ExecutableFileSectionInfo { unsigned tag; };
struct CodeHitData { unsigned tag; };
namespace DiskCache {using CodeHitData=::CodeHitData;}
static unsigned image_calls,cache_calls;
struct Cache {
    bool read,write;
    bool IsReadingDiskCache(){return read;}
    bool IsWritingDiskCache(){return write;}
    std::optional<CodeHitData> Lookup(int*,std::optional<ExecutableFileSectionInfo> region,uint64_t rip,std::optional<uint64_t>& key){
        assert(read&&region&&region->tag==42&&rip==0x401000);++cache_calls;key=123;return CodeHitData{17};
    }
};
struct Handler {
    std::optional<ExecutableFileSectionInfo> LookupExecutableFileSection(int*,uint64_t rip){
        assert(rip==0x401000);++image_calls;return ExecutableFileSectionInfo{42};
    }
};
int main(){
    for(int flags=0;flags<8;flags++){
        Cache DiskCache{bool(flags&1),bool(flags&2)};int *Thread=nullptr;
        int writer;int *CodeMapWriter=(flags&4)?&writer:nullptr;
        Handler handler;Handler *SyscallHandler=&handler;uint64_t GuestRIP=0x401000;
        image_calls=cache_calls=0;
        for(int n=0;n<10000;n++){
''' + gate + r'''
            assert(bool(Region)==bool(flags));
            assert(bool(Hit)==bool(flags&1)&&bool(DiskCacheGuestCodeKey)==bool(flags&1));
        }
        assert(image_calls==(flags?10000u:0u));
        assert(cache_calls==((flags&1)?10000u:0u));
    }
    puts("PASS exact metadata gates: OFF avoids 10000 image locks/lookups and cache calls; all 8 read/write/codemap combinations retain required metadata/hits/keys.");
}
'''
    with tempfile.TemporaryDirectory() as d:
        cpp, exe = Path(d)/'test.cpp', Path(d)/'test'
        cpp.write_text(harness)
        subprocess.run(['clang++','-std=c++20','-O1','-fsanitize=address,undefined',
                        '-fno-sanitize-recover=all',str(cpp),'-o',str(exe)],check=True)
        output = subprocess.check_output([str(exe)],text=True)
    build = json.loads((a.work/'module/build.json').read_text())
    patches = json.loads((a.work/'module/patches.json').read_text())
    assert any(entry['path']=='FEXCore/Source/Interface/Core/Core.cpp' and entry['patched_sha256']==sha(source) for entry in patches['files'])
    # Build provenance records all modified FEX source hashes.
    assert sha(a.work/'module/libwow64fex.dll') == build['sha256']
    assert sha(ROOT/'tools/fex_horizon_patches.py') == build['adapter_sources']['tools/fex_horizon_patches.py']
    report={'passed':True,'hardware_tested':False,'dll_sha256':build['sha256'],
            'generated_source_sha256':sha(source),'patches_sha256':sha(a.work/'module/patches.json'),
            'checks':output.strip(),'source_hashes':{name:sha(ROOT/name) for name in
                ('tests/fex_jit_metadata.py','tools/fex_horizon_patches.py')}}
    (a.work/'jit-metadata.json').write_text(json.dumps(report,indent=2)+'\n')
    print(output,end='')


if __name__ == '__main__':
    main()
