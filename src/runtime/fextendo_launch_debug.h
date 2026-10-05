/* LGPL-2.1-or-later. Bounded startup/error capture. No file I/O, allocation,
 * producer waits, Wine calls or exception handling in the capture path. */
#ifndef FEXTENDO_LAUNCH_DEBUG_H
#define FEXTENDO_LAUNCH_DEBUG_H
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdarg.h>
#include <stdio.h>
#include <errno.h>
#ifndef FX_LAUNCH_DEBUG_NOW
#define FX_LAUNCH_DEBUG_NOW() (armTicksToNs(armGetSystemTick())/1000000ull)
#endif
#define FX_DEBUG_LINES 64
#define FX_DEBUG_COLS 108
#define FX_DEBUG_PENDING_BYTES (64u*1024u)
struct fx_debug_snapshot { char lines[FX_DEBUG_LINES][FX_DEBUG_COLS+1];unsigned count,dropped;uint64_t elapsed_ms; };
static struct { char lines[FX_DEBUG_LINES][FX_DEBUG_COLS+1];unsigned head,count,column; } fx_debug_ring;
static unsigned fx_debug_enabled,fx_debug_lock,fx_debug_dropped;
static uint64_t fx_debug_origin;
static unsigned fx_debug_startup;
static char fx_debug_pending[FX_DEBUG_PENDING_BYTES];
static unsigned fx_debug_pending_size,fx_debug_file_capture;
static int fx_debug_try(void){unsigned n=0;return __atomic_compare_exchange_n(&fx_debug_lock,&n,1,0,__ATOMIC_ACQUIRE,__ATOMIC_RELAXED);}
static void fx_debug_unlock(void){__atomic_store_n(&fx_debug_lock,0,__ATOMIC_RELEASE);}
int wine_nx_launch_debug_active(void){return __atomic_load_n(&fx_debug_enabled,__ATOMIC_RELAXED)!=0;}
static int fx_launch_debug_startup(void){return __atomic_load_n(&fx_debug_startup,__ATOMIC_ACQUIRE)!=0;}
static void fx_debug_complete_line(void){
    /* Caller holds the RAM ring lock. The maintenance thread owns file I/O. */
    if(!fx_debug_ring.column)return;
    if(fx_debug_file_capture){
        unsigned n=fx_debug_ring.column;
        if(n+1<=FX_DEBUG_PENDING_BYTES-fx_debug_pending_size){
            memcpy(fx_debug_pending+fx_debug_pending_size,fx_debug_ring.lines[fx_debug_ring.head],n);
            fx_debug_pending_size+=n;fx_debug_pending[fx_debug_pending_size++]='\n';
        }else __atomic_add_fetch(&fx_debug_dropped,1,__ATOMIC_RELAXED);
    }
    fx_debug_ring.column=0;fx_debug_ring.head=(fx_debug_ring.head+1)%FX_DEBUG_LINES;
}
static __attribute__((noinline,used)) void fx_launch_debug_begin(int enabled){
    /* Called by the launcher before publishing its launch command. */
    __atomic_store_n(&fx_debug_enabled,0,__ATOMIC_RELEASE);
    __atomic_store_n(&fx_debug_startup,0,__ATOMIC_RELEASE);
    if(!enabled)return;
    if(!fx_debug_try())return;
    memset(&fx_debug_ring,0,sizeof(fx_debug_ring));fx_debug_origin=FX_LAUNCH_DEBUG_NOW();
    fx_debug_pending_size=0;fx_debug_file_capture=1;
    __atomic_store_n(&fx_debug_dropped,0,__ATOMIC_RELAXED);
    fx_debug_unlock();__atomic_store_n(&fx_debug_startup,1,__ATOMIC_RELEASE);
    __atomic_store_n(&fx_debug_enabled,1,__ATOMIC_RELEASE);
}
void wine_nx_launch_debug_write(const char *s,size_t size){
    if(!wine_nx_launch_debug_active()||!s||!size)return;
    int saved=errno;
    if(!fx_debug_try()){__atomic_add_fetch(&fx_debug_dropped,1,__ATOMIC_RELAXED);errno=saved;return;}
    if(size>4096){size=4096;__atomic_add_fetch(&fx_debug_dropped,1,__ATOMIC_RELAXED);}
    for(size_t i=0;i<size;i++){
        unsigned char ch=(unsigned char)s[i];if(ch=='\r')continue;
        if(ch=='\n'){
            fx_debug_complete_line();
            continue;
        }
        if(ch=='\t')ch=' ';else if(ch<32||ch>126)ch='?';
        if(!fx_debug_ring.column){
            char *line=fx_debug_ring.lines[fx_debug_ring.head];memset(line,0,FX_DEBUG_COLS+1);
            uint64_t now=FX_LAUNCH_DEBUG_NOW(),ms=now>=fx_debug_origin?now-fx_debug_origin:0;
            fx_debug_ring.column=(unsigned)snprintf(line,FX_DEBUG_COLS,"[%llu.%03llu] ",
                (unsigned long long)(ms/1000),(unsigned long long)(ms%1000));
            if(fx_debug_ring.count<FX_DEBUG_LINES)fx_debug_ring.count++;
        }
        fx_debug_ring.lines[fx_debug_ring.head][fx_debug_ring.column++]=(char)ch;
        if(fx_debug_ring.column==FX_DEBUG_COLS)fx_debug_complete_line();
    }
    fx_debug_unlock();errno=saved;
}
static void fx_launch_debug_log(const char *fmt,...){
    if(!wine_nx_launch_debug_active())return;
    int saved=errno;char line[768];va_list args;va_start(args,fmt);
    int n=vsnprintf(line,sizeof(line)-1,fmt,args);va_end(args);
    if(n>0){size_t len=(unsigned)n<sizeof(line)-1?(size_t)n:sizeof(line)-2;
        line[len++]='\n';wine_nx_launch_debug_write(line,len);}
    errno=saved;
}
static int fx_launch_debug_snapshot(struct fx_debug_snapshot *out){
    if(!fx_debug_try())return 0;
    unsigned end=fx_debug_ring.head+(fx_debug_ring.column!=0);
    out->count=fx_debug_ring.count;out->dropped=__atomic_load_n(&fx_debug_dropped,__ATOMIC_RELAXED);
    for(unsigned i=0;i<out->count;i++)
        memcpy(out->lines[i],fx_debug_ring.lines[(end+FX_DEBUG_LINES-out->count+i)%FX_DEBUG_LINES],FX_DEBUG_COLS+1);
    uint64_t now=FX_LAUNCH_DEBUG_NOW();out->elapsed_ms=now>=fx_debug_origin?now-fx_debug_origin:0;
    fx_debug_unlock();return 1;
}
unsigned char wine_nx_launch_debug_flags(const char *channel){
    if(!wine_nx_launch_debug_active())return 0;
    /* Wine enum: fixme=0 err=1 warn=2 trace=3. Trace just module loading,
     * avoiding per-call rendering/input floods and unsafe lazy argv parsing. */
    unsigned char flags=6;
    if(fx_launch_debug_startup()&&channel&&(!strcmp(channel,"loaddll")||!strcmp(channel,"module")))flags|=8;
    return flags;
}
static __attribute__((noinline,used)) void fx_launch_debug_handoff(void){
    if(__atomic_exchange_n(&fx_debug_startup,0,__ATOMIC_ACQ_REL))
        fx_launch_debug_log("[HANDOFF] startup console closed; game owns the screen; error logging continues in fex-runtime.log");
}
#endif
