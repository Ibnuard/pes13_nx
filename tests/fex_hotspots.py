"""Sanitizer tests of bounded compile telemetry and FEX sampler metadata/resume.

Clock, mapping and SVC boundaries are modeled. Production bodies are executed;
reports bind them to the generated sources and final ELF/DLL. Not device timing.
"""
from pathlib import Path
import argparse, hashlib, json, re, subprocess, sys, tempfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from fex_resume_patches import _function

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def body(name):
    return re.sub(r'^#include [^\n]+\n|^#pragma once\n', '', (ROOT/name).read_text(), flags=re.M)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--work',type=Path,required=True)
    a=p.parse_args(); records=[]
    runtime=json.loads((a.work/'runtime/runtime-build.json').read_text())
    module=json.loads((a.work/'module/build.json').read_text())
    patches=json.loads((a.work/'runtime/wine-patches.json').read_text())
    filename='wine-nx-probe/source/thread_profile.c'
    source=(a.source/filename).read_text()
    assert patches['native-source'][filename]==sha(a.source/filename)
    assert runtime['native_elf_sha256']==sha(a.work/'runtime/reference/pes13-fex.elf')
    assert module['sha256']==sha(a.work/'module/libwow64fex.dll')
    for name in ('src/fex/module_compile_trace.cpp','src/fex/horizon_compile_trace.h','tools/fex_compile_trace_patches.py'):
        assert module['adapter_sources'][name]==sha(ROOT/name)
    for name in ('src/runtime/fex_hot_profile.h','tools/fex_fast_api_patches.py'):
        assert runtime['patch_sources'][name]==sha(ROOT/name)
    with tempfile.TemporaryDirectory(prefix='fex-hotspots-') as tmp:
        tmp=Path(tmp)
        def run(name,code):
            cpp=tmp/(name+'.cpp');cpp.write_text(code);exe=tmp/name
            subprocess.run(['clang++','-std=c++20','-O1','-g','-pthread','-fsanitize=address,undefined',
                '-fno-sanitize-recover=all','-I',str(ROOT),str(cpp),'-o',str(exe)],check=True)
            output=subprocess.check_output([str(exe)],text=True,timeout=60).strip()
            records.append(output);print(output)
        run('compile',r'''
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <thread>
#include <cstdio>
static std::atomic<uint64_t> tick{1};
static uint64_t freq=1000000;
uint64_t pes13_fex_counter(){return tick.load();}
uint64_t pes13_fex_counter_frequency(){return freq;}
static std::vector<std::string> lines;
void PES13FexLog(const char *s){assert(strlen(s)<768);lines.emplace_back(s);}
'''+body('src/fex/horizon_compile_trace.h')+body('src/fex/module_compile_trace.cpp')+r'''
using namespace FexCompileTraceDetail;
static void reset(){for(auto &r:Rows)r={};Totals={};Lost=0;lines.clear();Busy.clear();}
static void event(uint64_t rip,uint64_t duration,unsigned outcome=1){
 PES13FexCompileTrace t(rip);t.outcome=outcome;t.instructions=20;t.host_bytes=128;tick+=duration;
}
int main(){
 unsetenv("FEXTENDO_TRACE");PES13FexCompileTraceInit();event(0x401000,10);assert(!Totals.calls);
 setenv("FEXTENDO_TRACE","1",1);freq=0;PES13FexCompileTraceInit();event(0x401000,10);assert(!Totals.calls);
 freq=1000000;PES13FexCompileTraceInit();tick=100;
 {
  PES13FexCompileTrace t(0x401000);t.outcome=1;
  {PES13FexCompilePhase front(t.Phases(),2);
   {PES13FexCompilePhase decode(t.Phases(),0);tick+=3;}
   {PES13FexCompilePhase passes(t.Phases(),1);tick+=5;}
   tick+=2;
  }
  {PES13FexCompilePhase back(t.Phases(),3);tick+=7;}
 }
 assert(Totals.calls==1&&Totals.total==17&&Totals.phases[0]==3&&Totals.phases[1]==5&&Totals.phases[2]==10&&Totals.phases[3]==7);
 event(0x401000,9,2);event(0x401000,4,0);
 PES13FexCompileTraceReport(tick);
 assert(lines.size()==2&&lines[1].find("calls=3 total_us=30 peak_us=17")!=std::string::npos);
 assert(lines[1].find("generated=1 raced=1 empty=1")!=std::string::npos);
 PES13FexCompileTraceReport(tick);assert(lines.size()==2);reset();
 // Reporting sorts retained rows by total cost and clears the window.
 for(unsigned i=1;i<=20;i++)event(0x401000+i*4,i);
 PES13FexCompileTraceReport(tick);assert(lines.size()==13&&lines[1].find("total_us=20 ")!=std::string::npos);
 assert(lines.back().find("total_us=9 ")!=std::string::npos);reset();
 // Deliberately exceed the bounded probe chain; total still accounts these.
 uint64_t rip=4;unsigned inserted=0;
 for(;inserted<Probes+1;rip+=4)if((((rip>>2)^(rip>>16))&(Slots-1))==1){event(rip,1);inserted++;}
 assert(Totals.calls==Probes+1&&Lost==1);reset();
 Busy.test_and_set();event(0x401000,10);assert(!Totals.calls&&Lost==1);
 PES13FexCompileTraceReport(tick);assert(lines.empty());Busy.clear();
 PES13FexCompileTraceReport(tick);assert(lines.size()==1&&lines[0].find("lost=1")!=std::string::npos);reset();
 // No producer waits under contention. Accepted + dropped conserves attempts.
 std::vector<std::thread> threads;
 for(int i=0;i<8;i++)threads.emplace_back([]{for(int n=0;n<4000;n++)event(0x401000,1);});
 for(auto &t:threads)t.join();assert(Totals.calls+Lost==32000);reset();
 // Reordered completion keeps the earliest begin/latest end, not insertion order.
 tick=500;auto *late=new PES13FexCompileTrace(0x401000);tick=100;
 auto *early=new PES13FexCompileTrace(0x401000);tick=600;delete late;tick=200;delete early;
 assert(Totals.first==100&&Totals.last==600);reset();
 tick=100;{PES13FexCompileTrace t(0x401000);tick=99;}assert(!Totals.calls);
 // Maximum-width data exercises the fixed output buffer under ASan.
 freq=1;Frequency=1;Row max{};max.rip=max.calls=max.total=max.peak=max.first=max.last=UINT64_MAX;
 max.instructions=max.bytes=max.generated=max.raced=max.empty=UINT64_MAX;
 for(auto &p:max.phases)p=UINT64_MAX;Emit("[FEX3-COMPILE]",max,UINT64_MAX,UINT64_MAX);
 assert(lines.size()==1);puts("PASS compile phases, nested frontend, aggregation, top 12, bounded collision/contention loss, concurrent conservation, reset, clock reversal, output bounds");
}
''')
        # Execute exact metadata helper with modeled readable ranges.
        run('metadata',r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include "src/fex/horizon_stall.h"
struct Reg {uint64_t x;};struct ThreadContext {Reg pc,cpu_gprs[29];};
static unsigned char state[128],code[1024];static int alias_mode=1,reads;
static void *alias(const void *p,uint64_t){return alias_mode==1?(void*)123:alias_mode==2?const_cast<void*>(p):nullptr;}
struct Host {void *(*write_alias)(const void*,uint64_t);} host{alias};
static Host *pes13_fex_native_host(){return &host;}
static int fex_stall_read(uint64_t addr,void *out,size_t len){
 ++reads;for(auto base:{(uintptr_t)state,(uintptr_t)code}){
 size_t size=base==(uintptr_t)state?sizeof(state):sizeof(code);
 if(addr>=base&&addr-base<=size&&len<=size-(addr-base)){memcpy(out,(void*)addr,len);return 1;}}
 return 0;
}
'''.replace('#include <cstdio>','#include <cstdio>\n#include <initializer_list>')+body('src/runtime/fex_hot_profile.h')+r'''
int main(){ThreadContext c{};uintptr_t out;uint64_t block=(uintptr_t)code;
 uint32_t offset=256;pes13_fex_observed_tail tail{512,0x401000};
 auto init=[&]{alias_mode=1;memcpy(state,&block,8);memcpy(code,&offset,4);memcpy(code+offset,&tail,sizeof(tail));c.cpu_gprs[28].x=(uintptr_t)state;c.pc.x=block+64;};
 auto reject=[&]{out=0xbad;assert(!fex_hot_pc(&c,&out)&&out==0xbad);};
 init();assert(fex_hot_pc(&c,&out)&&out==0x401000);
 alias_mode=0;reads=0;reject();assert(!reads);alias_mode=2;reject();assert(!reads);
 init();c.cpu_gprs[28].x=0;reject();c.cpu_gprs[28].x=UINT64_MAX;reject();
 init();uint64_t bad=UINT64_MAX;memcpy(state,&bad,8);reject();
 init();uint32_t bad_offset=16*1024*1024;memcpy(code,&bad_offset,4);reject();
 init();bad_offset=1000;memcpy(code,&bad_offset,4);reject();
 for(uint64_t size:{255ull,270ull,16777217ull}){init();memcpy(code+offset,&size,8);reject();}
 init();c.pc.x=block-1;reject();c.pc.x=block+512;reject();
 for(uint64_t rip:{0ull,0x100000000ull}){init();memcpy(code+offset+8,&rip,8);reject();}
 puts("PASS FEX metadata: owned RX only, valid block label, unreadable/overflowing state and tail, wrong PC range, invalid guest entry");}
''')
        # Extract one exact sampling iteration and test every pause/context/resume
        # combination. This catches early returns that could strand a thread.
        start=source.index('            if (!target->handle) continue;')
        end=source.index('\n        }\n        pthread_mutex_unlock',start)
        iteration=source[start:end]
        run('resume',r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
using Result=int;struct ThreadContext{int unused;};
struct Target{int handle,missed;} slot;
static int pause_status,context_status,resume_fail_count,pauses,resumes,contexts,sleeps,records;
static uint64_t fex_hot_pauses,fex_hot_pause_ticks,fex_hot_peak_ticks,fex_hot_resume_failures,clocktick;
#define ThreadActivity_Paused 1
#define ThreadActivity_Runnable 0
#define R_FAILED(v) ((v)!=0)
#define R_SUCCEEDED(v) ((v)==0)
static Result svcSetThreadActivity(int,int kind){if(kind){pauses++;return pause_status;}return ++resumes<=resume_fail_count;}
static Result svcGetThreadContext3(ThreadContext*,int){contexts++;return context_status;}
static void svcSleepThread(int){sleeps++;}
static uint64_t armGetSystemTick(){return ++clocktick;}
static unsigned walk_callers(ThreadContext*,uint64_t*){return 0;}
static int fex_hot_pc(ThreadContext*,uintptr_t*){return 0;}
static void record(Target*,ThreadContext*,int,uintptr_t,uint64_t*,unsigned,uintptr_t*,unsigned){assert(resumes);records++;}
static void sample(){for(int i=0;i<1;i++){Target *target=&slot;ThreadContext ctx;Result rc;unsigned tries,count,x86_count;int translated;uintptr_t x86=0,x86_callers[12];uint64_t callers[12];
'''+iteration+r'''
}}
int main(){for(int handle=0;handle<2;handle++)for(int p=0;p<2;p++)for(int c=0;c<2;c++)for(int r=0;r<3;r++){
 slot={handle,0};pause_status=p;context_status=c;resume_fail_count=r;pauses=resumes=contexts=sleeps=records=0;
 auto before=fex_hot_resume_failures;sample();
 if(!handle){assert(!pauses&&!resumes&&!contexts);continue;}
 assert(pauses==1);if(p){assert(!resumes&&!contexts&&slot.missed==1);continue;}
 assert(resumes==(r?2:1)&&contexts==(c?2:1)&&sleeps==(c?1:0));
 assert(fex_hot_resume_failures-before==(r==2)&&slot.missed==c&&records==!c);
}puts("PASS sampler exact iteration: absent target, failed pause, bounded context retry, immediate resume and retry, failure counters, recording after resume");}
''')
    report={'passed':True,'hardware_tested':False,'native_elf_sha256':runtime['native_elf_sha256'],
        'dll_sha256':module['sha256'],'generated_sampler_sha256':sha(a.source/filename),
        'checks':records,'scope':__doc__,'source_hashes':{name:sha(ROOT/name) for name in (
            'tests/fex_hotspots.py','src/fex/horizon_compile_trace.h','src/fex/module_compile_trace.cpp',
            'src/runtime/fex_hot_profile.h','tools/fex_compile_trace_patches.py','tools/fex_fast_api_patches.py')}}
    (a.work/'hotspots.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
