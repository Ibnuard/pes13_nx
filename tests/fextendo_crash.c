/* Direct fatal persistence with no worker, modeled native FS and termination. */
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <setjmp.h>
#include <pthread.h>
typedef uint32_t Result,u32;
typedef uint64_t u64;
typedef struct {u64 addr,size;u32 type,attr,perm;} MemoryInfo;
enum {Perm_R=1};
static unsigned char nro[128];
static _Alignas(16) uintptr_t test_frames[24];
static int query_fail,query_unreadable;
static Result svcQueryMemory(MemoryInfo *info,u32 *page,u64 address){
    assert(address!=0);*page=0;
    *info=(MemoryInfo){.addr=(uintptr_t)nro,.size=sizeof(nro),.perm=query_unreadable?0:Perm_R};
    if(address>=(uintptr_t)test_frames&&address<(uintptr_t)test_frames+sizeof(test_frames))
        *info=(MemoryInfo){.addr=(uintptr_t)test_frames,.size=sizeof(test_frames),.perm=query_unreadable?0:Perm_R};
    return query_fail?1:0;
}
typedef struct {unsigned handle;} FsFile;
typedef struct {unsigned handle;} FsFileSystem;
typedef int FsDirEntryType;
enum {FsDirEntryType_File=1,FsOpenMode_Write=2,FsWriteOption_None=0,FsWriteOption_Flush=1};
#define R_FAILED(x) ((x)!=0)
#define R_SUCCEEDED(x) ((x)==0)
typedef union {uint64_t x;} CpuRegister;
typedef struct {u32 error_desc,pad[3];CpuRegister cpu_gprs[29],fp,lr,sp,pc;
    uint64_t padding;unsigned char fpu_gprs[512];u32 pstate,afsr0,afsr1,esr;CpuRegister far;} ThreadExceptionDump;
static FsFileSystem fs;
static char disk[18432],previous[18432];
static int exists,previous_exists,writes,flushes,fail_write,fail_rotate,fail_open,fail_create,reenter;
static unsigned fs_calls,breaks,aborts,diag_aborts;
static uint64_t clock_tick=19200000;
static jmp_buf terminated;
static Result last_code;
static uintptr_t last_address,last_size;
void wine_nx_crash_exception(const void *,unsigned);
static FsFileSystem *fsdevGetDeviceFileSystem(const char *s){assert(!strcmp(s,"sdmc"));fs_calls++;return &fs;}
static Result fsFsGetEntryType(FsFileSystem *f,const char *p,FsDirEntryType *t){
    assert(f==&fs);fs_calls++;*t=FsDirEntryType_File;
    return (strstr(p,"previous")?previous_exists:exists)?0:1;
}
static Result fsFsDeleteFile(FsFileSystem *f,const char *p){
    assert(f==&fs&&strstr(p,"previous"));fs_calls++;previous_exists=0;return 0;
}
static Result fsFsRenameFile(FsFileSystem *f,const char *a,const char *b){
    assert(f==&fs&&!strstr(a,"previous")&&strstr(b,"previous"));fs_calls++;
    if(fail_rotate)return 1;
    memcpy(previous,disk,sizeof(disk));previous_exists=1;exists=0;return 0;
}
static Result fsFsCreateFile(FsFileSystem *f,const char *p,uint64_t size,unsigned flags){
    assert(f==&fs&&!strstr(p,"previous")&&size==sizeof(disk)&&!flags);fs_calls++;
    if(fail_create||exists)return 1;
    memset(disk,0,sizeof(disk));exists=1;return 0;
}
static Result fsFsOpenFile(FsFileSystem *f,const char *p,unsigned mode,FsFile *out){
    assert(f==&fs&&!strstr(p,"previous")&&mode==FsOpenMode_Write);fs_calls++;
    if(fail_open)return 1;
    out->handle=42;return 0;
}
static Result fsFileWrite(FsFile *f,uint64_t off,const void *data,uint64_t size,unsigned flags){
    assert(f->handle==42&&off+size<=sizeof(disk)&&size==2048);fs_calls++;writes++;
    if(reenter){reenter=0;wine_nx_crash_exception(NULL,0xbad);}
    if(fail_write)return 0xdead;
    memcpy(disk+off,data,size);if(flags==FsWriteOption_Flush)flushes++;
    return 0;
}
static void fsFileClose(FsFile *f){assert(f->handle==42);fs_calls++;}
static uint64_t armGetSystemTick(void){return clock_tick;}
static uint64_t armTicksToNs(uint64_t n){return n*1000000000/19200000;}
static unsigned threadGetCurHandle(void){return 0x1234;}
#ifdef FX_NATIVE_ABORT_DETAIL
#include "../src/runtime/fextendo_transition_trace.h"
#endif
#include "../src/runtime/fextendo_crash.h"
void __real_abort(void){aborts++;longjmp(terminated,1);}
void __real_diagAbortWithResult(Result r){diag_aborts++;last_code=r;longjmp(terminated,2);}
Result __real_svcBreak(u32 r,uintptr_t a,uintptr_t s){breaks++;last_code=r;last_address=a;last_size=s;return 0x6789;}
static void reboot(void){
    fx_crash_ready=fx_crash_lock=fx_crash_records=fx_crash_dropped=0;
    fail_write=fail_rotate=fail_open=fail_create=reenter=0;
    fx_crash_bootstrap();
}
static void contains(const char *text){assert(memmem(disk,sizeof(disk),text,strlen(text)));}
static void *concurrent(void *unused){(void)unused;for(unsigned i=0;i<1000;i++)wine_nx_crash_exit(42);return NULL;}
int main(void){
    _Static_assert(offsetof(ThreadExceptionDump,pc)==0x110,"real ABI PC");
    _Static_assert(offsetof(ThreadExceptionDump,far)==0x330,"real ABI FAR");
    fx_crash_failure_line((void *)1);wine_nx_crash_exception((void *)1,0);assert(!fs_calls);
    memcpy(nro+0x10,"NRO0",4);for(unsigned i=0;i<32;i++)nro[0x40+i]=(unsigned char)i;
    reboot();assert(fx_crash_ready&&flushes==1&&writes==10);
#if FX_SCRATCH_RESERVE_VERSION == 3
#if defined(FX_RUST_HEAP)
    contains("Candidate=high-native-heap-v1");
#elif FX_SCRATCH_PAGES >= 2
    contains("Candidate=high-fragmented-heap-v1");
#elif defined(FX_SCRATCH_PAGES)
    contains("Candidate=high-scratch-pages-v1");
#elif defined(FX_THREAD_STACK_RESERVE)
    contains("Candidate=high-thread-stack-v1");
#elif defined(FX_PAGE_STORE)
    contains("Candidate=high-page-store-v1");
#else
    contains("Candidate=high-scratch64-v1");
#endif
#endif
    contains("nro_build_id=000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f");
    unsigned baseline=fs_calls;
    fx_crash_failure_line("");fx_crash_failure_line("[");fx_crash_failure_line("[FEX] normal message");
    fx_crash_failure_line("[FEX] cache failed, can retry");wine_nx_crash_exit(0);
    assert(fs_calls==baseline);
    fx_crash_settings(3,1);wine_nx_crash_fex_image(0xff540000,0x410000);
    fx_crash_failure_line("[FEX2-HEAP] STOP compiler scratch failed\nforged");
    assert(flushes==2);contains("RECORD=FEX_STOP");contains("failed?forged");
    ThreadExceptionDump ctx={0};ctx.pc.x=0xff68bb88;ctx.far.x=0x9876;ctx.sp.x=0xabcdef;
    ctx.esr=0xf0000000;ctx.error_desc=0x104;
    for(unsigned i=0;i<29;i++)ctx.cpu_gprs[i].x=i+0x1000;
    clock_tick+=19200000;reenter=1;wine_nx_crash_exception(&ctx,0x80000003);
    assert(flushes==3&&fx_crash_dropped==1);
    contains("pc=0x00000000ff68bb88");contains("x28=0x000000000000101c");
    contains("elapsed_ms=0x00000000000003e8");contains("fex_base=0x00000000ff540000");
    if(!setjmp(terminated))__wrap_abort();assert(aborts==1);contains("RECORD=NATIVE_ABORT");
    if(!setjmp(terminated))__wrap_diagAbortWithResult(0xface);assert(diag_aborts==1&&last_code==0xface);
    baseline=fs_calls;
    assert(__wrap_svcBreak(0x80000000,1,2)==0x6789&&fs_calls==baseline);
    assert(__wrap_svcBreak(3,0x123,0x456)==0x6789&&last_code==3&&last_address==0x123&&last_size==0x456);
    contains("RECORD=SVC_BREAK");
    char saved[sizeof(disk)];memcpy(saved,disk,sizeof(disk));
    reboot();assert(!memcmp(previous,saved,sizeof(disk))&&fx_crash_ready);
    contains("Status=armed");assert(!memmem(disk,sizeof(disk),"RECORD=",7));
    pthread_t threads[8];
    for(unsigned i=0;i<8;i++)assert(!pthread_create(&threads[i],NULL,concurrent,NULL));
    for(unsigned i=0;i<8;i++)pthread_join(threads[i],NULL);
    assert(fx_crash_records==8&&!fx_crash_lock);baseline=fs_calls;
    wine_nx_crash_exception((void *)1,1);assert(fs_calls==baseline);
    reboot();fail_write=1;wine_nx_crash_exit(13);assert(fx_crash_last_result==0xdead&&!fx_crash_lock);
    fail_write=0;wine_nx_crash_exit(14);contains("code=0x000000000000000e");
    memcpy(saved,disk,sizeof(disk));fx_crash_ready=0;fail_rotate=1;fx_crash_init(nro);
    assert(!fx_crash_ready&&!memcmp(disk,saved,sizeof(disk)));
    for(unsigned error=1;error<=3;error++){
        exists=previous_exists=fx_crash_ready=0;fail_rotate=0;
        fail_create=error==1;fail_open=error==2;fail_write=error==3;
        fx_crash_init(nro);assert(!fx_crash_ready);
    }
    query_fail=1;reboot();contains("nro_build_id=unavailable");
    assert(fx_crash_ready&&!fx_crash_nro_base);
    query_fail=0;query_unreadable=1;reboot();contains("nro_build_id=unavailable");
    query_unreadable=0;reboot();assert(fx_crash_nro_base==(uintptr_t)nro);
#ifdef FX_NATIVE_ABORT_DETAIL
    fx_tr_enabled=1;
    test_frames[0]=(uintptr_t)&test_frames[2];test_frames[1]=0x87c8c;
    test_frames[2]=(uintptr_t)&test_frames[2];test_frames[3]=0x885f8; /* cycle */
    const char text[]="memory allocation of 131077 bytes failed\n";
    wine_nx_transition_text(text,sizeof(text)-1);
    wine_nx_transition_alloc_site(1,131077,64,0x12345,12);
    assert(fx_crash_begin("NATIVE_CONTEXT"));fx_crash_native_detail((uintptr_t)test_frames);fx_crash_end();
    contains("bt00=0x0000000000087c8c");contains("bt01=0x00000000000885f8");
    contains("alloc_size=0x0000000000020005");contains("native_text_tail=memory allocation");
    assert(!memmem(disk,sizeof(disk),"bt02=",5));
    reboot();query_unreadable=1;
    assert(fx_crash_begin("NATIVE_CONTEXT"));fx_crash_native_detail((uintptr_t)test_frames);fx_crash_end();
    assert(!memmem(disk,sizeof(disk),"bt00=",5));query_unreadable=0;
    reboot();fx_tr_lock=1;
    assert(fx_crash_begin("NATIVE_CONTEXT"));fx_crash_native_detail(1);fx_crash_end();
    contains("trace_busy=0x0000000000000001");fx_tr_lock=0;
#endif
    reboot();wine_nx_crash_rust_allocation(3,131077,64,65536,0x12345);
    contains("RECORD=RUST_ALLOCATION_FAILED");contains("old_size=0x0000000000010000");
    puts("PASS: direct fatal flush, full context, no routine writes, rotation, bounded concurrent/reentrant failure, I/O errors and original termination semantics");
}
