"""Probe safety, generated environment and hooks, tied to final ELF and FEX DLL."""
from pathlib import Path
import argparse, hashlib, json, re, subprocess, sys, tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from fex_resume_patches import _function

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--work',type=Path,required=True);a=p.parse_args()
    runtime=(a.source/'wine-nx-probe/source/runtime.c').read_text()
    sync=(a.source/'dlls/ntdll/unix/sync.c').read_text()
    elf=a.work/'runtime/reference/pes13-fex.elf';dll=a.work/'module/libwow64fex.dll'
    records=[]
    with tempfile.TemporaryDirectory(prefix='fextendo-short-') as tmp:
        tmp=Path(tmp)
        def run(name,source,lang='c'):
            path=tmp/(name+'.'+lang);path.write_text(source);exe=tmp/name
            cmd=['clang++' if lang=='cpp' else 'clang','-std=c++20' if lang=='cpp' else '-std=gnu11','-O1','-g',
                 '-Wall','-Wextra','-fsanitize=address,undefined','-fno-sanitize-recover=all','-pthread','-I',str(ROOT/'tests'),str(path),'-o',str(exe)]
            subprocess.run(cmd,check=True)
            result=subprocess.run([str(exe)],check=True,text=True,capture_output=True,timeout=60)
            records.append(result.stdout.strip());print(records[-1])
        run('native',(ROOT/'tests/fex_short_trace.c').read_text())
        body=re.sub(r'^#include [^\n]+\n','',(ROOT/'src/fex/module_jit_timing.cpp').read_text(),flags=re.M)
        harness='''
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
#include <thread>
#include <mutex>
struct __TEB { struct { void *UniqueThread; } ClientId; };
static thread_local __TEB test_teb{{(void*)4}};
static __TEB *NtCurrentTeb(){return &test_teb;}
std::atomic<uint64_t> clock_ticks{19200000};
uint64_t pes13_fex_counter(){return clock_ticks.load();}
uint64_t pes13_fex_counter_frequency(){return 19200000;}
std::mutex mutex;std::vector<std::string> messages;
void PES13FexLog(const char *line){std::lock_guard<std::mutex> lock(mutex);messages.emplace_back(line);}
'''+re.sub(r'^#include [^\n]+\n|^#pragma once\n','',
          (ROOT/'src/fex/horizon_compile_trace.h').read_text()+'\n'+
          (ROOT/'src/fex/module_compile_trace.cpp').read_text(),flags=re.M)+body+(ROOT/'tests/fex_short_module.cpp.inc').read_text()
        run('module',harness,'cpp')
        # Run exact generated env append: existing entries/terminators survive ON/OFF.
        start=runtime.index('    {\n        static char short_environment[8192];')
        end=runtime.index('    chars += environment_bytes;',start)
        envbody=runtime[start:end]
        run('env','''
#include <assert.h>
#include <string.h>
#include <stdio.h>
static int fex_short_enabled;
int main(){for(int enabled=0;enabled<2;enabled++){
    const char original[]="FEX_MAXINST=500\\0KEEP=value\\0";
    const char *environment=original;size_t environment_bytes=sizeof(original);
    fex_short_enabled=enabled;
'''+envbody+'''
    assert(!memcmp(original,environment,sizeof(original)-1));
    assert(!strcmp(environment+sizeof(original)-1,enabled?"FEXTENDO_TRACE=1":"FEXTENDO_TRACE=0"));
    assert(environment[environment_bytes-1]==0&&environment[environment_bytes-2]==0);
}puts("PASS exact launch environment ON/OFF preserves original entries and double terminator");}
''')
        # Execute the actual public wrappers with controlled original statuses.
        wrappers='\n'.join(_function(sync.replace('NTSTATUS WINAPI '+n+'(', 'static NTSTATUS WINAPI '+n+'('),n) for n in ('NtWaitForAlertByThreadId','NtAlertThreadByThreadId'))
        run('wrappers','''
#include <assert.h>
#include <stdint.h>
#include <errno.h>
#include <stdio.h>
#define WINAPI
#define HandleToULong(x) ((unsigned)(uintptr_t)(x))
typedef unsigned NTSTATUS;typedef void *HANDLE;typedef int64_t LARGE_INTEGER;
struct {struct {void *UniqueThread;} ClientId;} test_teb={{(void*)4}};
#define NtCurrentTeb() (&test_teb)
static unsigned status,seen_tid,seen_result,seen_target;static const void *seen_address;static const LARGE_INTEGER *seen_timeout;
static NTSTATUS fex_short_NtWaitForAlertByThreadId(const void *p,const LARGE_INTEGER *t){assert(errno==7);seen_address=p;seen_timeout=t;errno=99;return status;}
static NTSTATUS fex_short_NtAlertThreadByThreadId(HANDLE t){seen_target=HandleToULong(t);errno=98;return status;}
uint64_t wine_nx_fex_short_wait_begin(unsigned t){seen_tid=t;errno=61;return 123;}
void wine_nx_fex_short_wait_end(unsigned t,uint64_t b,uint64_t object,unsigned r){assert(t==4&&b==123&&object==(uintptr_t)&status);seen_result=r;errno=62;}
void wine_nx_fex_short_alert(unsigned target,unsigned caller,unsigned r){assert(target==164&&caller==4);seen_result=r;errno=63;}
'''+wrappers+'''
int main(){unsigned statuses[]={0,0x101,0x102,0xc0000008,0xc000000d};LARGE_INTEGER timeout=-100;
for(unsigned i=0;i<5;i++){status=statuses[i];errno=7;assert(NtWaitForAlertByThreadId(&status,&timeout)==status);assert(errno==99&&seen_tid==4&&seen_result==status&&seen_address==&status&&seen_timeout==&timeout);
assert(NtAlertThreadByThreadId((HANDLE)164)==status);assert(errno==98&&seen_result==status&&seen_target==164);}
puts("PASS generated wrappers preserve statuses, errno, arguments and timeout pointer");}
''')
    objdump='/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump'
    for function,calls in {
        'NtWaitForAlertByThreadId':['wine_nx_fex_short_wait_begin','wine_nx_fex_short_wait_end'],
        'NtAlertThreadByThreadId':['wine_nx_fex_short_alert'],
        'wine_nx_fex_pipeline_note':['fex_short_push'],
    }.items():
        code=subprocess.check_output([objdump,'-d','--disassemble='+function,str(elf)],text=True)
        for call in calls:assert re.search(r'\bbl\s+[0-9a-f]+ <'+call+r'>',code),(function,call)
    assert '[FEX3-JIT-THREAD] ' in dll.read_bytes().decode('latin1')
    records.append('Final ELF calls wait/alert/stage hooks; final FEX DLL contains per-thread records.')
    sources=['tests/fex_short_trace.py','tests/fex_short_trace.c','tests/fex_short_module.cpp.inc','src/runtime/fex_short_trace.h',
             'src/fex/module_jit_timing.cpp','src/fex/module_compile_trace.cpp','src/fex/horizon_compile_trace.h','tools/fex_short_trace_patches.py']
    report={'passed':True,'hardware_tested':False,'native_elf_sha256':sha(elf),'dll_sha256':sha(dll),
            'source_hashes':{n:sha(ROOT/n) for n in sources},'checks':records}
    (a.work/'short-trace.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
