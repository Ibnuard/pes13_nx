"""Exercise actual JIT metric/profile bodies and both generated environments."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from fex_resume_patches import _function


def main():
    if not __debug__: raise RuntimeError('Assertions required')
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    runtime_path = args.source/'wine-nx-probe/source/runtime.c'
    runtime = runtime_path.read_text()
    environments = {}
    for name, value in [('runtime_environment', '500'), ('fex_jit_large_environment', '5000'), ('fex_jit_small_environment', '128')]:
        block = re.search(r'static const char '+name+r'\[\] =\n(.*?);\n', runtime, re.S).group(1)
        entries = re.findall(r'    "(.*)"', block)
        assert sum(e.startswith('FEX_MAXINST=') for e in entries) == 1
        assert 'FEX_MAXINST='+value+r'\0' in entries
        environments[name] = entries
    baseline = [e for e in environments['runtime_environment'] if not e.startswith('FEX_MAXINST=')]
    for label in ('fex_jit_large_environment','fex_jit_small_environment'):
        assert baseline == [e for e in environments[label] if not e.startswith('FEX_MAXINST=')]
    # Execute the actual startup branch, including flags and disk-cache mapping.
    declarations = '\n'.join(re.findall(r'static const char (?:runtime_environment|fex_jit_(?:large|small)_environment)(?:_disk)?\[\] =\n.*?";\n', runtime, re.S))
    start = runtime.index('        environment = runtime_environment;')
    end = runtime.index('        log_line("[PES13-GFX]', start)
    branch = runtime[start:end]
    envtest = r'''
#include <assert.h>
#include <stddef.h>
#include <string.h>
#define RUNTIME_DIR "root"
#define log_line(...) ((void)0)
static int small,large,disk;
static int wine_nx_config_file_bool(const char *key,int fallback){
    (void)fallback;return strstr(key,"small")?small:strstr(key,"large")?large:disk;
}
'''+declarations+r'''
int main(){for(small=0;small<2;small++)for(large=0;large<2;large++)for(disk=0;disk<2;disk++){
    const char *environment;size_t environment_bytes;
'''+branch+r'''
    const char *wanted=large?"FEX_MAXINST=5000":small?"FEX_MAXINST=128":"FEX_MAXINST=500";
    int found=0,cache=0;size_t n=0;
    while(n+1<environment_bytes){
        const char *entry=environment+n;
        found+=!strcmp(entry,wanted);cache+=!strcmp(entry,disk?"FEX_DISKCACHE=1":"FEX_DISKCACHE=0");
        n+=strlen(entry)+1;
    }
    assert(found==1&&cache==1&&n==environment_bytes-1&&environment[n]==0);
}}
'''
    with tempfile.TemporaryDirectory(prefix='fex-jit-env-') as d:
        c, exe = Path(d)/'env.c', Path(d)/'env'
        c.write_text(envtest)
        subprocess.run(['clang','-std=c11','-O1','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(c),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True,timeout=30)
    def body(name):
        return re.sub(r'^#include [^\n]+\n', '', (ROOT/'src/fex'/name).read_text(), flags=re.M)
    harness = r'''
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <string>
#include <vector>
#include <thread>
#include <map>
struct __TEB {struct {void *UniqueThread;} ClientId;};
static __TEB test_teb{{(void*)4}};
static __TEB *NtCurrentTeb(){return &test_teb;}
std::atomic<uint64_t> clock_ticks{19200000};
uint64_t pes13_fex_counter() { return clock_ticks.load(); }
uint64_t pes13_fex_counter_frequency() { return 19200000; }
std::mutex log_mutex;
std::vector<std::string> messages;
extern "C" void PES13FexLog(const char *s) { std::lock_guard<std::mutex> l(log_mutex); messages.emplace_back(s); }
enum { PES13_FEX_CONTROL, PES13_FEX_FAST, PES13_FEX_FASTEST, PES13_FEX_FAST_VECTOR };
unsigned profile;
unsigned PES13FexPerformanceProfile() { return profile; }
int requested;
namespace FEXCore::Config {
enum { CONFIG_X87REDUCEDPRECISION, CONFIG_TSOENABLED, CONFIG_VECTORTSOENABLED,
       CONFIG_MEMCPYSETTSOENABLED, CONFIG_HALFBARRIERTSOENABLED, CONFIG_MULTIBLOCK,
       CONFIG_MAXINST, CONFIG_SMCCHECKS, CONFIG_SMC_MTRACK=1 };
std::map<int,std::string> config;
void Set(int k, const char *v) { config[k]=v; }
}
#define FEX_CONFIG_OPT(name, opt) auto name = [] { return requested; }
'''
    harness += body('horizon_jit_timing.h').replace('#pragma once', '')
    harness += body('horizon_compile_trace.h').replace('#pragma once','')
    harness += body('module_compile_trace.cpp')
    harness += body('module_jit_timing.cpp') + body('module_profile.cpp')
    harness += _function(runtime, 'fex_warm_routine_line')
    harness += r'''
int main() {
    using namespace FEXCore::Config;
    for(profile=0;profile<4;++profile) for(int n:{-1,0,1,127,128,129,500,5000,9000}) {
        requested=n; PES13FexApplyPerformanceProfile();
        assert(config[CONFIG_MAXINST]==(profile && n==128 ? "128" : profile && n==500 ? "500" : "5000"));
        assert(config[CONFIG_TSOENABLED]==(profile==PES13_FEX_FASTEST ? "0" : "1"));
        assert(config[CONFIG_MULTIBLOCK]=="1" && config[CONFIG_SMCCHECKS]=="1");
    }
    unsetenv("FEXTENDO_TRACE");
    PES13FexJitTimingInit();
    auto start=PES13FexJitBegin();
    clock_ticks=start+19200000/50; PES13FexJitEnd(1,start);
    assert(Stats[1].slow20==0);
    clock_ticks++; PES13FexJitEnd(1,start);
    assert(Stats[1].slow20==1);
    clock_ticks=start+19200000/20; PES13FexJitEnd(1,start);
    assert(Stats[1].slow50==0);
    clock_ticks++; PES13FexJitEnd(1,start);
    assert(Stats[1].slow50==1);
    PES13FexJitEnd(5,start); PES13FexJitEnd(1,clock_ticks+1);
    assert(Stats[1].count==4);
    std::vector<std::thread> threads;
    for(int i=0;i<8;++i) threads.emplace_back([start]{
        for(int j=0;j<2000;++j) PES13FexJitEnd(2,start);
    });
    for(auto &t:threads) t.join();
    assert(Stats[2].count==16000 && Stats[2].slow50==16000);
    clock_ticks=Origin+19200000ull*5;
    size_t old=messages.size();
    threads.clear();
    for(int i=0;i<8;++i) threads.emplace_back([]{PES13FexJitReport();});
    for(auto &t:threads) t.join();
    assert(messages.size()==old+3);
    for(size_t i=old;i<messages.size();++i) {
        assert(messages[i].find("uptime_ms=5000")!=std::string::npos);
        assert(fex_warm_routine_line(messages[i].c_str()));
    }
    PES13FexJitReport(); assert(messages.size()==old+3);
    assert(!fex_warm_routine_line("[FEX3-JIT] allocation failure"));
    puts("PASS 36 profile combinations; 16000 concurrent samples; thresholds and report gate; three environments; deferred metrics only");
}
'''
    with tempfile.TemporaryDirectory(prefix='fex-jit-test-') as d:
        cpp, binary = Path(d)/'test.cpp', Path(d)/'test'
        cpp.write_text(harness)
        subprocess.run(['clang++','-std=c++20','-O1','-g','-pthread','-fsanitize=address,undefined',
                        '-fno-sanitize-recover=all',str(cpp),'-o',str(binary)],check=True)
        output = subprocess.check_output([str(binary)],text=True,timeout=30)
    report={'passed':True,'hardware_tested':False,'output':output,
            'runtime_source_sha256':hashlib.sha256(runtime_path.read_bytes()).hexdigest(),
            'sources':{n:hashlib.sha256((ROOT/'src/fex'/n).read_bytes()).hexdigest() for n in
                       ['module_profile.cpp','module_jit_timing.cpp','horizon_jit_timing.h',
                        'module_compile_trace.cpp','horizon_compile_trace.h']}}
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(output,end='')


if __name__ == '__main__': main()
