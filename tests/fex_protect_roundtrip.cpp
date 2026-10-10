// Test services for the real FEX tracker and WOW64 notification extracted by
// fex_protect_roundtrip.py. NT metadata is modeled; mmap/mprotect are real.
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <limits>
#include <map>
#include <mutex>
#include <shared_mutex>
#include <string_view>
#include <thread>
#include <unordered_map>
#include <utility>
#include <vector>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>
#include <signal.h>
#include <sys/resource.h>
using ULONG = uint32_t; using DWORD = uint32_t; using SIZE_T = size_t;
using BOOL = int; using HMODULE = void*; using LPCVOID = const void*;
constexpr ULONG PAGE_NOACCESS=1, PAGE_READONLY=2, PAGE_READWRITE=4, PAGE_WRITECOPY=8,
 PAGE_EXECUTE=0x10, PAGE_EXECUTE_READ=0x20, PAGE_EXECUTE_READWRITE=0x40,
 PAGE_EXECUTE_WRITECOPY=0x80, PAGE_GUARD=0x100, MEM_COMMIT=0x1000, MEM_EXECUTE_OPTION_ENABLE=2;
constexpr ULONG BAD=0xc000000d, MEM_FREE=0x10000;
constexpr int MemoryBasicInformation=0;
static void* NtCurrentProcess() { return reinterpret_cast<void*>(intptr_t(-1)); }
struct MEMORY_BASIC_INFORMATION { void* BaseAddress{}; void* AllocationBase{}; SIZE_T RegionSize{}; ULONG State{}, Protect{}; };
struct IMAGE_SECTION_HEADER { ULONG VirtualAddress; struct { ULONG VirtualSize; } Misc; ULONG Characteristics; };
struct IMAGE_NT_HEADERS { struct { unsigned NumberOfSections; } FileHeader; IMAGE_SECTION_HEADER sections[1]; };
constexpr ULONG IMAGE_SCN_MEM_EXECUTE=0x20000000, IMAGE_SCN_MEM_WRITE=0x80000000;
#define IMAGE_FIRST_SECTION(p) ((p)->sections)
static IMAGE_NT_HEADERS* RtlImageNtHeader(HMODULE p) { return static_cast<IMAGE_NT_HEADERS*>(p); }
namespace fextl { template<class T> using vector=std::vector<T>; }
namespace LogMan::Msg {
 template<class... T> void DFmt(const char*,T...) {}
 template<class... T> void IFmt(const char*,T...) {}
}
namespace FEXCore {
namespace Utils { constexpr uint64_t FEX_PAGE_SIZE=4096, FEX_PAGE_MASK=~uint64_t(4095); }
namespace Config { constexpr int CONFIG_SMC_NONE=0; }
namespace Core { struct InternalThreadState {}; }
namespace HLE { struct ExecutableRangeInfo { uint64_t Base,Size; bool Writable; }; }
namespace Context {
struct CheckedMutex {
 std::mutex mutex; std::atomic<bool> held{false};
 void lock() { mutex.lock(); assert(!held.exchange(true)); }
 void unlock() { assert(held.exchange(false)); mutex.unlock(); }
};
struct Context {
 CheckedMutex code; unsigned invalidations{};
 auto& GetCodeInvalidationMutex() { return code; }
 void InvalidateCodeBuffersCodeRange(uint64_t,uint64_t) { assert(code.held); ++invalidations; }
 void InvalidateThreadCachedCodeRange(Core::InternalThreadState*,uint64_t,uint64_t) { assert(code.held); }
 bool IsAddressInCodeBuffer(Core::InternalThreadState*,uint64_t) { return false; }
 uint64_t RestoreRIPFromHostPC(Core::InternalThreadState*,uint64_t) { return 0; }
 uint64_t GetGuestBlockEntry(Core::InternalThreadState*) { return 0; }
 void MarkMonoBackpatcherBlock(uint64_t) {}
 void MarkMonoDetected() {}
};
}
}
static int SMCMode=1;
struct ConfigOpt { int value; operator int() const { return value; } int operator()() const { return value; } };
#define FEX_CONFIG_OPT(name,key) ConfigOpt name{SMCMode}
struct PES13FexJitScope { explicit PES13FexJitScope(int) {} };
static unsigned protect_errors=0, query_calls=0, protect_calls=0;
static void PES13FexLogSMCProtectFailure(uint64_t,uint64_t,uint32_t,uint32_t) { ++protect_errors; }
static void PES13FexLog(const char*) {}
struct Page { ULONG prot; bool image; };
static std::map<uint64_t,Page> pages;
static bool fail_query=false, fail_next_protect=false;
static SIZE_T VirtualQuery(LPCVOID, MEMORY_BASIC_INFORMATION*, SIZE_T) { return 0; }
static ULONG NtQueryVirtualMemory(void*,void* p,int,MEMORY_BASIC_INFORMATION* info,SIZE_T,void*) {
 ++query_calls;
 const auto page=reinterpret_cast<uint64_t>(p)&~uint64_t(4095);
 auto it=pages.find(page);
 if(fail_query||it==pages.end()) return BAD;
 *info={reinterpret_cast<void*>(page),reinterpret_cast<void*>(page),4096,MEM_COMMIT,it->second.prot};
 return 0;
}
static int linux_prot(ULONG p) {
 if((p&PAGE_GUARD)||p==PAGE_NOACCESS) return PROT_NONE;
 return PROT_READ | ((p&(PAGE_READWRITE|PAGE_WRITECOPY|PAGE_EXECUTE_READWRITE|PAGE_EXECUTE_WRITECOPY))?PROT_WRITE:0);
}
static ULONG NtProtectVirtualMemory(void*,void** p,SIZE_T* size,ULONG prot,ULONG* old) {
 ++protect_calls;
 if(fail_next_protect) { fail_next_protect=false; return BAD; }
 const auto address=reinterpret_cast<uint64_t>(*p);
 if(!*size||address>UINT64_MAX-(*size-1)) return BAD;
 const auto base=address&~uint64_t(4095), end=(address+*size-1)&~uint64_t(4095);
 if(end-base>1024*4096) return BAD;
 for(auto page=base;;page+=4096) { if(!pages.count(page))return BAD; if(page==end)break; }
 *old=pages.at(base).prot;
 for(auto page=base;;page+=4096) {
  auto& value=pages.at(page);
  value.prot=prot;
  if(value.image&&prot==PAGE_EXECUTE_READWRITE)value.prot=PAGE_EXECUTE_WRITECOPY;
  assert(!mprotect(reinterpret_cast<void*>(page),4096,linux_prot(value.prot)));
  if(page==end)break;
 }
 *p=reinterpret_cast<void*>(base);*size=end-base+4096;
 return 0;
}

// INSERT_REAL_FEX_HERE

static std::mutex ThreadCreationMutex;
static FEX::Windows::InvalidationTracker* InvalidationTracker;

// INSERT_REAL_NOTIFICATION_HERE

struct Fixture {
 FEXCore::Context::Context ctx;
 std::unordered_map<DWORD,FEXCore::Core::InternalThreadState*> threads;
 FEX::Windows::InvalidationTracker tracker{ctx,threads};
 void* allocation; uint64_t base;
 explicit Fixture(ULONG prot=PAGE_EXECUTE_READWRITE,bool image=false) {
  allocation=mmap(nullptr,3*4096,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
  assert(allocation!=MAP_FAILED);base=reinterpret_cast<uint64_t>(allocation);
  for(unsigned i=0;i<3;i++)pages[base+i*4096]={prot,image};
  if(image&&prot==PAGE_EXECUTE_READWRITE)for(auto& entry:pages)entry.second.prot=PAGE_EXECUTE_WRITECOPY;
  tracker.HandleMemoryProtectionNotification(base,3*4096,prot);
  InvalidationTracker=&tracker;
 }
 ~Fixture() { assert(!ctx.code.held);munmap(allocation,3*4096);pages.clear();fail_query=false;fail_next_protect=false; }
 ULONG protect(uint64_t address,SIZE_T count,ULONG value,ULONG& old, bool fail=false) {
  BTCpuNotifyMemoryProtect(reinterpret_cast<void*>(address),count,value,0,0);
  if(fail)fail_next_protect=true;
  void* p=reinterpret_cast<void*>(address);auto size=count;
  ULONG result=NtProtectVirtualMemory(NtCurrentProcess(),&p,&size,value,&old);
  BTCpuNotifyMemoryProtect(p,size,value,1,result);
  assert(!ctx.code.held);
  return result;
 }
 void trap(unsigned index=0) { std::scoped_lock lock(ctx.code);tracker.ReprotectRWXIntervals(base+index*4096,4096); }
 bool write(unsigned offset=0) {
  auto child=fork(); assert(child>=0);
  if(!child) { signal(SIGSEGV,SIG_DFL);rlimit no_core{0,0};setrlimit(RLIMIT_CORE,&no_core);
   *reinterpret_cast<volatile unsigned char*>(base+offset)=0x42;_exit(0); }
  int status;assert(waitpid(child,&status,0)==child);
  return WIFEXITED(status)&&WEXITSTATUS(status)==0;
 }
};

int main() {
 unsigned checks=0;
 for(bool image:{false,true}) {
  Fixture f(PAGE_EXECUTE_READWRITE,image);f.trap();assert(!f.write(0x42));
  ULONG old=0;assert(!f.protect(f.base+0x42,4,PAGE_EXECUTE_READWRITE,old));
#if FIXED_BUILD
  assert(old==(image?PAGE_EXECUTE_WRITECOPY:PAGE_EXECUTE_READWRITE));
#else
  assert(old==PAGE_EXECUTE_READ); // Reproduces the delivered bug.
#endif
  ULONG unused=0;assert(!f.protect(f.base+0x42,4,old,unused));
  f.trap();
  auto handled=f.tracker.HandleRWXAccessViolation(nullptr,0,f.base+0x42);
  assert(handled==bool(FIXED_BUILD));assert(f.write(0x42)==bool(FIXED_BUILD));
  ++checks;
 }
 { // Ordinary RX text patched then restored must remain RX and fast.
  Fixture f(PAGE_EXECUTE_READ); ULONG old=0,unused=0;
  assert(!f.protect(f.base,4096,PAGE_EXECUTE_READWRITE,old));assert(old==PAGE_EXECUTE_READ);
  assert(!f.protect(f.base,4096,old,unused));
  assert(!f.tracker.QueryExecutableRange(f.base).Writable);
  assert(!f.tracker.HandleRWXAccessViolation(nullptr,0,f.base));assert(!f.write());++checks;
 }
 { // Explicit guest readonly is respected even on an initially writable page.
  Fixture f;f.trap();ULONG old=0;assert(!f.protect(f.base,4096,PAGE_EXECUTE_READ,old));
  assert(!f.tracker.QueryExecutableRange(f.base).Writable);
  assert(!f.tracker.HandleRWXAccessViolation(nullptr,0,f.base));assert(!f.write());++checks;
 }
 { // A failed API call preserves outputs and restores the old SMC trap.
  Fixture f;f.trap();ULONG old=0x1234;
  assert(f.protect(f.base+3,100,PAGE_READONLY,old,true)==BAD);assert(old==0x1234);
  assert(pages.at(f.base).prot==PAGE_EXECUTE_READ);assert(!f.write());
  assert(f.tracker.QueryExecutableRange(f.base).Writable);++checks;
 }
 { // Only the first page supplies old protection; the adjacent page is untouched.
  Fixture f;f.trap();f.trap(1);ULONG old=0;
  assert(!f.protect(f.base+5,1,PAGE_EXECUTE_READWRITE,old));
  assert(pages.at(f.base+4096).prot==PAGE_EXECUTE_READ);assert(!f.write(4096));++checks;
 }
 { // Guards and unrelated noaccess pages are not silently untrapped.
  Fixture f;for(ULONG prot:{PAGE_EXECUTE_READ|PAGE_GUARD,PAGE_NOACCESS}) {
   pages.at(f.base).prot=prot;unsigned before=protect_calls;ULONG old=0;
   assert(f.protect(f.base,4096,PAGE_READONLY,old,true)==BAD);
   assert(protect_calls==before+1);assert(pages.at(f.base).prot==prot);
  }++checks;
 }
 { // No action for an invalid or zero-sized guest range.
  Fixture f;unsigned before=protect_calls;ULONG old=0;
  assert(f.protect(f.base,0,PAGE_READONLY,old)==BAD);
  assert(f.protect(UINT64_MAX-2,10,PAGE_READONLY,old)==BAD);
  assert(protect_calls==before+2);++checks;
 }
 { // Failed queries/untrap attempts do not skip the actual guest operation.
  Fixture f;f.trap();fail_query=true;ULONG old=0;
  assert(!f.protect(f.base,4096,PAGE_EXECUTE_READWRITE,old));assert(old==PAGE_EXECUTE_READ);
  fail_query=false;f.trap();fail_next_protect=true;
#if FIXED_BUILD
  assert(!f.protect(f.base,4096,PAGE_EXECUTE_READWRITE,old));assert(protect_errors>0);
#else
  assert(f.protect(f.base,4096,PAGE_EXECUTE_READWRITE,old)==BAD);
#endif
  ++checks;
 }
#if FIXED_BUILD
 { // A compiler cannot reapply RX between pre-notify and the native call.
  Fixture f;f.trap();BTCpuNotifyMemoryProtect(f.allocation,4096,PAGE_EXECUTE_READWRITE,0,0);
  std::atomic<bool> started{false},finished{false};
  std::thread compiler([&] { started=true;{std::scoped_lock lock(f.ctx.code);f.tracker.ReprotectRWXIntervals(f.base,4096);}finished=true; });
  while(!started)std::this_thread::yield();
  std::this_thread::sleep_for(std::chrono::milliseconds(20));assert(!finished);
  void* p=f.allocation;SIZE_T size=4096;ULONG old=0;
  assert(!NtProtectVirtualMemory(NtCurrentProcess(),&p,&size,PAGE_EXECUTE_READWRITE,&old));
  assert(old==PAGE_EXECUTE_READWRITE);
  BTCpuNotifyMemoryProtect(p,size,PAGE_EXECUTE_READWRITE,1,0);compiler.join();assert(finished);++checks;
 }
#endif
 printf("{\"passed\":true,\"fixed\":%s,\"cases\":%u,\"actual_linux_page_protection\":true}\n",FIXED_BUILD?"true":"false",checks);
}
