/* LGPL-2.1-or-later. Best-effort fatal evidence, independent of trace worker.
 * Bootstrap owns rotation/open/preallocation. Fatal paths use fixed storage,
 * bounded formatting and one flushed native FS write, without stdio/heap or
 * waiting for our lock. FS IPC can still fail/block; this is not an OS dump.
 */
#ifndef FEXTENDO_CRASH_H
#define FEXTENDO_CRASH_H
#include <stdint.h>
#include <stddef.h>
/* Wine deliberately poisons the old Windows `far` keyword. The SDK dump has
 * a field with this name; restore Wine's macro after this native-only header. */
#pragma push_macro("far")
#undef far

#define FX_CRASH_BYTES 2048
#define FX_CRASH_RECORDS 8
#define FX_CRASH_PATH "/switch/pes13-fex/crash.log"
#define FX_CRASH_PREVIOUS "/switch/pes13-fex/crash.previous.log"
static FsFile fx_crash_file;
static unsigned fx_crash_ready,fx_crash_lock,fx_crash_records;
static unsigned fx_crash_preset,fx_crash_renderer;
static uint64_t fx_crash_start,fx_crash_nro_base,fx_crash_fex_base,fx_crash_fex_size;
static uint64_t fx_crash_dropped;
static Result fx_crash_last_result;
static char fx_crash_buffer[FX_CRASH_BYTES];
static unsigned fx_crash_length;

static void fx_crash_char(char c){
    if(fx_crash_length<FX_CRASH_BYTES-32)fx_crash_buffer[fx_crash_length++]=c;
}
static void fx_crash_text(const char *s){
    while(*s&&fx_crash_length<FX_CRASH_BYTES-32)fx_crash_char(*s++);
}
static void fx_crash_hex(uint64_t n){
    static const char digits[]="0123456789abcdef";
    for(int shift=60;shift>=0;shift-=4)fx_crash_char(digits[(n>>shift)&15]);
}
static void fx_crash_value(const char *key,uint64_t n){
    fx_crash_text(key);fx_crash_text("=0x");fx_crash_hex(n);fx_crash_char('\n');
}
static void fx_crash_reset(void){
    for(unsigned i=0;i<FX_CRASH_BYTES;i++)fx_crash_buffer[i]='\n';
    fx_crash_length=0;
}
static void fx_crash_write(unsigned block){
    fx_crash_text("END_RECORD\n");
    fx_crash_last_result=fsFileWrite(&fx_crash_file,(uint64_t)block*FX_CRASH_BYTES,
                                    fx_crash_buffer,FX_CRASH_BYTES,FsWriteOption_Flush);
}
/* Called only at bootstrap, before guest threads. All file names are fixed. */
static __attribute__((noinline,used)) void fx_crash_init(const unsigned char *nro){
    FsFileSystem *fs=fsdevGetDeviceFileSystem("sdmc");
    if(!fs)return;
    FsDirEntryType type;
    Result rc=fsFsGetEntryType(fs,FX_CRASH_PATH,&type);
    if(R_SUCCEEDED(rc)){
        /* Never truncate the current evidence if its rotation fails. */
        if(type!=FsDirEntryType_File)return;
        if(R_SUCCEEDED(fsFsGetEntryType(fs,FX_CRASH_PREVIOUS,&type))){
            if(type!=FsDirEntryType_File||R_FAILED(fsFsDeleteFile(fs,FX_CRASH_PREVIOUS)))return;
        }
        if(R_FAILED(fsFsRenameFile(fs,FX_CRASH_PATH,FX_CRASH_PREVIOUS)))return;
    }
    if(R_FAILED(fsFsCreateFile(fs,FX_CRASH_PATH,FX_CRASH_BYTES*(FX_CRASH_RECORDS+1),0)))return;
    if(R_FAILED(fsFsOpenFile(fs,FX_CRASH_PATH,FsOpenMode_Write,&fx_crash_file)))return;
    fx_crash_start=armGetSystemTick();fx_crash_nro_base=(uintptr_t)nro;
    /* Allocate clusters and write readable empty records before memory pressure. */
    fx_crash_reset();
    for(unsigned i=0;i<=FX_CRASH_RECORDS;i++){
        rc=fsFileWrite(&fx_crash_file,(uint64_t)i*FX_CRASH_BYTES,
                       fx_crash_buffer,FX_CRASH_BYTES,FsWriteOption_None);
        if(R_FAILED(rc)){fsFileClose(&fx_crash_file);return;}
    }
#if defined(FX_RUST_HEAP)
    fx_crash_text("FEXTENDO_CRASH_V2\nCandidate=high-native-heap-v1\n");
#elif FX_SCRATCH_PAGES >= 2
    fx_crash_text("FEXTENDO_CRASH_V2\nCandidate=high-fragmented-heap-v1\n");
#elif defined(FX_SCRATCH_PAGES)
    fx_crash_text("FEXTENDO_CRASH_V2\nCandidate=high-scratch-pages-v1\n");
#elif defined(FX_THREAD_STACK_RESERVE)
    fx_crash_text("FEXTENDO_CRASH_V2\nCandidate=high-thread-stack-v1\n");
#elif defined(FX_PAGE_STORE)
    fx_crash_text("FEXTENDO_CRASH_V2\nCandidate=high-page-store-v1\n");
#elif FX_SCRATCH_RESERVE_VERSION == 3
    fx_crash_text("FEXTENDO_CRASH_V2\nCandidate=high-scratch64-v1\n");
#else
    fx_crash_text("FEXTENDO_CRASH_V2\nCandidate=high-live-freeze-v1\n");
#endif
    fx_crash_text("Status=armed; only records below indicate a captured failure.\n");
    fx_crash_text("No records does not prove a clean exit. Numeric fields are hexadecimal.\n");
    fx_crash_value("session_tick",fx_crash_start);fx_crash_value("nro_base",fx_crash_nro_base);
    fx_crash_text("nro_build_id=");
    if(nro&&nro[0x10]=='N'&&nro[0x11]=='R'&&nro[0x12]=='O'&&nro[0x13]=='0'){
        static const char digits[]="0123456789abcdef";
        for(unsigned i=0x40;i<0x60;i++){
            fx_crash_char(digits[nro[i]>>4]);fx_crash_char(digits[nro[i]&15]);
        }
    }else fx_crash_text("unavailable");
    fx_crash_char('\n');fx_crash_write(0);
    if(R_FAILED(fx_crash_last_result)){fsFileClose(&fx_crash_file);return;}
    __atomic_store_n(&fx_crash_ready,1,__ATOMIC_RELEASE);
}
/* __start__ is an absolute-zero linker symbol on this target. Resolve the
 * real text mapping via a live code address instead of dereferencing zero. */
static __attribute__((noinline,used)) void fx_crash_bootstrap(void){
    MemoryInfo info;u32 page;
    const unsigned char *nro=NULL;
    if(R_SUCCEEDED(svcQueryMemory(&info,&page,(u64)(uintptr_t)&fx_crash_bootstrap))&&
       (info.perm&Perm_R)&&info.size>=0x80&&info.addr)
        nro=(const unsigned char *)(uintptr_t)info.addr;
    fx_crash_init(nro);
}
void wine_nx_crash_fex_image(uint64_t base,uint64_t size){
    __atomic_store_n(&fx_crash_fex_size,size,__ATOMIC_RELAXED);
    __atomic_store_n(&fx_crash_fex_base,base,__ATOMIC_RELEASE);
}
static void fx_crash_settings(unsigned preset,unsigned renderer){
    __atomic_store_n(&fx_crash_preset,preset,__ATOMIC_RELAXED);
    __atomic_store_n(&fx_crash_renderer,renderer,__ATOMIC_RELAXED);
}
static int fx_crash_begin(const char *kind){
    if(!__atomic_load_n(&fx_crash_ready,__ATOMIC_ACQUIRE))return 0;
    unsigned expected=0;
    if(!__atomic_compare_exchange_n(&fx_crash_lock,&expected,1,0,__ATOMIC_ACQUIRE,__ATOMIC_RELAXED)){
        __atomic_add_fetch(&fx_crash_dropped,1,__ATOMIC_RELAXED);return 0;
    }
    if(fx_crash_records>=FX_CRASH_RECORDS){
        __atomic_store_n(&fx_crash_lock,0,__ATOMIC_RELEASE);return 0;
    }
    fx_crash_reset();fx_crash_text("RECORD=");fx_crash_text(kind);fx_crash_char('\n');
    fx_crash_value("sequence",++fx_crash_records);
    fx_crash_value("session_tick",fx_crash_start);
    fx_crash_value("elapsed_ms",armTicksToNs(armGetSystemTick()-fx_crash_start)/1000000);
    fx_crash_value("thread_handle",threadGetCurHandle());
    fx_crash_value("preset",__atomic_load_n(&fx_crash_preset,__ATOMIC_RELAXED));
    fx_crash_value("renderer",__atomic_load_n(&fx_crash_renderer,__ATOMIC_RELAXED));
    fx_crash_value("nro_base",fx_crash_nro_base);
    fx_crash_value("fex_base",__atomic_load_n(&fx_crash_fex_base,__ATOMIC_ACQUIRE));
    fx_crash_value("fex_size",__atomic_load_n(&fx_crash_fex_size,__ATOMIC_RELAXED));
    fx_crash_value("dropped_reentrant",__atomic_load_n(&fx_crash_dropped,__ATOMIC_RELAXED));
    return 1;
}
static void fx_crash_end(void){
    fx_crash_write(fx_crash_records);
    __atomic_store_n(&fx_crash_lock,0,__ATOMIC_RELEASE);
}
void wine_nx_crash_exception(const void *dump,unsigned status){
    if(!fx_crash_begin("UNHANDLED_NATIVE_EXCEPTION"))return;
    const ThreadExceptionDump *ctx=dump;
    fx_crash_value("status",status);
    if(ctx){
        fx_crash_value("description",ctx->error_desc);fx_crash_value("esr",ctx->esr);
        fx_crash_value("pc",ctx->pc.x);fx_crash_value("far",ctx->far.x);
        fx_crash_value("sp",ctx->sp.x);fx_crash_value("lr",ctx->lr.x);fx_crash_value("fp",ctx->fp.x);
        for(unsigned i=0;i<29;i++){
            char key[4]={'x',(char)('0'+i/10),(char)('0'+i%10),0};
            fx_crash_value(key,ctx->cpu_gprs[i].x);
        }
    }
    fx_crash_end();
}
void wine_nx_crash_exit(unsigned code){
    if(!code||!fx_crash_begin("NONZERO_GUEST_EXIT"))return;
    fx_crash_value("code",code);fx_crash_end();
}
static void fx_crash_failure_line(const char *s){
    if(!__atomic_load_n(&fx_crash_ready,__ATOMIC_ACQUIRE)||!s)return;
    if(s[0]!='['||s[1]!='F'||s[2]!='E'||s[3]!='X')return;
    unsigned n=0;while(n<384&&s[n])n++;
    int stop=0;
    for(unsigned i=0;i+4<=n;i++)
        if(s[i]=='S'&&s[i+1]=='T'&&s[i+2]=='O'&&s[i+3]=='P'){stop=1;break;}
    if(!stop||!fx_crash_begin("FEX_STOP"))return;
    fx_crash_text("message=");
    for(unsigned i=0;i<n;i++)fx_crash_char(s[i]>=32&&s[i]<127?s[i]:'?');
    fx_crash_char('\n');fx_crash_end();
}
#ifdef FX_NATIVE_ABORT_DETAIL
/* Read only a monotonic frame chain inside the caller's current readable
 * mapping. No unwinder/heap, no other thread suspension, at most 12 frames.
 * A missing/unreadable/cyclic frame stops the walk; return PCs need -4 when
 * symbolicated on AArch64. This is best-effort, not a complete backtrace. */
static __attribute__((noinline,used)) void fx_crash_native_detail(uintptr_t fp){
    MemoryInfo info;u32 page;uintptr_t start=fp;
    if(fp&&!(fp&15)&&R_SUCCEEDED(svcQueryMemory(&info,&page,fp))&&
       (info.perm&Perm_R)&&fp>=info.addr&&info.size>=16&&fp-info.addr<=info.size-16){
        for(unsigned i=0;i<12;i++){
            if(!fp||(fp&15)||fp<start||fp-start>1024*1024||
               fp<info.addr||fp-info.addr>info.size-16)break;
            const volatile uintptr_t *frame=(const volatile uintptr_t *)fp;
            uintptr_t next=frame[0],ret=frame[1];
            char key[5]={'b','t',(char)('0'+i/10),(char)('0'+i%10),0};
            fx_crash_value(key,ret);
            if(next<=fp)break;
            fp=next;
        }
    }
    /* Include output still waiting for the periodic worker. Rust emits OOM
     * and panic text immediately before abort; otherwise that final subsecond
     * of evidence would be discarded at termination. Never wait on the lock. */
    if(!fx_tr_try()){fx_crash_value("trace_busy",1);return;}
    unsigned thread=threadGetCurHandle();
    for(unsigned n=fx_tr_alloc_count;n>0;n--){
        const struct fx_tr_alloc_site *a=&fx_tr_allocs[n-1];
        if(a->thread!=thread)continue;
        fx_crash_value("alloc_size",a->size);fx_crash_value("alloc_alignment",a->alignment);
        fx_crash_value("alloc_caller",a->caller);fx_crash_value("alloc_errno",a->error);
        break;
    }
    unsigned n=fx_tr_text_size<512?fx_tr_text_size:512;
    fx_crash_text("native_text_tail=");
    for(unsigned i=fx_tr_text_size-n;i<fx_tr_text_size;i++){
        unsigned char c=fx_tr_text[i];fx_crash_char(c>=32&&c<127?c:'?');
    }
    fx_crash_char('\n');fx_tr_unlock();
}
#endif
__attribute__((noinline,used)) void wine_nx_crash_rust_allocation(unsigned kind,size_t size,size_t alignment,size_t old_size,uintptr_t caller){
    if(!fx_crash_begin("RUST_ALLOCATION_FAILED"))return;
    fx_crash_value("kind",kind);fx_crash_value("size",size);
    fx_crash_value("alignment",alignment);fx_crash_value("old_size",old_size);
    fx_crash_value("caller",caller);fx_crash_end();
}
static void fx_crash_abort(const char *kind,uint64_t code,uint64_t address,uint64_t size,uintptr_t caller,uintptr_t fp){
    if(!fx_crash_begin(kind))return;
    fx_crash_value("code",code);fx_crash_value("address",address);
    fx_crash_value("size",size);fx_crash_value("caller",caller);
    /* Flush the primary record before touching even a checked frame chain. */
    fx_crash_end();
#ifdef FX_NATIVE_ABORT_DETAIL
    if(fx_crash_begin("NATIVE_CONTEXT")){
        fx_crash_value("caller",caller);fx_crash_native_detail(fp);fx_crash_end();
    }
#else
    (void)fp;
#endif
}
extern void __real_abort(void) __attribute__((noreturn));
extern void __real_diagAbortWithResult(Result) __attribute__((noreturn));
extern Result __real_svcBreak(u32,uintptr_t,uintptr_t);
void __wrap_abort(void){
    fx_crash_abort("NATIVE_ABORT",0,0,0,(uintptr_t)__builtin_return_address(0),(uintptr_t)__builtin_frame_address(0));
    __real_abort();
}
void __wrap_diagAbortWithResult(Result result){
    fx_crash_abort("LIBNX_ABORT",result,0,0,(uintptr_t)__builtin_return_address(0),(uintptr_t)__builtin_frame_address(0));
    __real_diagAbortWithResult(result);
}
Result __wrap_svcBreak(u32 reason,uintptr_t address,uintptr_t size){
    /* Debugger notification breaks are not crashes and may return normally. */
    if(!(reason&0x80000000u))
        fx_crash_abort("SVC_BREAK",reason,address,size,(uintptr_t)__builtin_return_address(0),(uintptr_t)__builtin_frame_address(0));
    return __real_svcBreak(reason,address,size);
}
#pragma pop_macro("far")
#endif
