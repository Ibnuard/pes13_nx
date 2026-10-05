#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <sys/stat.h>
#include <unistd.h>
static unsigned io_calls,writes;
static int fail_rename,fail_write;
static FILE *test_open(const char *p,const char *m){io_calls++;return fopen(p,m);}
static int test_stat(const char *p,struct stat *s){io_calls++;return stat(p,s);}
static int test_unlink(const char *p){io_calls++;return unlink(p);}
static int test_rename(const char *a,const char *b){io_calls++;if(fail_rename){errno=EACCES;return -1;}return rename(a,b);}
static size_t test_write(const void *p,size_t size,size_t n,FILE *f){writes++;if(fail_write){errno=ENOSPC;return 0;}return fwrite(p,size,n,f);}
#define fopen test_open
#define stat(...) test_stat(__VA_ARGS__)
#define unlink test_unlink
#define rename test_rename
#define fwrite test_write
#define FX_LAUNCH_DEBUG_NOW() 1000ull
#include "../src/runtime/fextendo_debug_file.h"
#undef fopen
#undef stat
#undef unlink
#undef rename
#undef fwrite
static char text[FX_DEBUG_FILE_LIMIT+256];
static void read_log(const char *path){FILE *f=fopen(path,"rb");assert(f);size_t n=fread(text,1,sizeof(text)-1,f);text[n]=0;assert(!fclose(f));}
int main(int argc,char **argv){
    assert(argc==2);char current[1024],previous[1024];
    snprintf(current,sizeof(current),"%s/fex-runtime.log",argv[1]);
    snprintf(previous,sizeof(previous),"%s/fex-runtime.previous.log",argv[1]);
    fx_debug_file_begin(0);assert(fx_debug_file_prepare((void *)1));
    fx_debug_file_tick();fx_launch_debug_log((void *)1);assert(!io_calls&&!writes);
    fx_debug_file_begin(1);fx_launch_debug_log("startup queued before file open");
    fx_debug_file_tick();assert(!io_calls&&!writes); /* no lost pre-open queue */
    assert(fx_debug_file_prepare(argv[1]));unsigned before=writes;
    fx_launch_debug_log("Wine loading");assert(writes==before);
    fx_debug_file_tick();read_log(current);assert(strstr(text,"startup queued before file open")&&strstr(text,"Wine loading"));
    assert(fx_launch_debug_startup());fx_launch_debug_handoff();assert(!fx_launch_debug_startup());
    assert(wine_nx_launch_debug_flags("module")==6);
    fx_launch_debug_log("error after handoff");fx_debug_file_tick();read_log(current);
    assert(strstr(text,"[HANDOFF]")&&strstr(text,"error after handoff"));
    before=writes;fx_debug_file_tick();assert(writes==before); /* idle has no write */
    fx_debug_file_begin(1);assert(fx_debug_file_prepare(argv[1]));read_log(previous);assert(strstr(text,"error after handoff"));
    for(int i=0;i<10000;i++)fx_launch_debug_log("error batch %d",i);
    assert(fx_debug_dropped&&fx_debug_pending_size<=FX_DEBUG_PENDING_BYTES);
    fx_debug_file_tick();read_log(current);assert(strstr(text,"dropped_messages="));
    /* Full storage disables only file logging; RAM console capture stays live. */
    fail_write=1;fx_launch_debug_log("full card");fx_debug_file_tick();fail_write=0;
    assert(!fx_debug_file_ready&&wine_nx_launch_debug_active());before=writes;
    fx_debug_file_tick();assert(writes==before);
    fx_debug_file_begin(1);fail_rename=1;assert(!fx_debug_file_prepare(argv[1]));fail_rename=0;
    read_log(current);assert(strstr(text,"dropped_messages=")); /* never truncated */
    fx_debug_file_begin(1);assert(fx_debug_file_prepare(argv[1]));
    for(unsigned i=0;i<1000&&fx_debug_file_ready;i++){
        for(unsigned j=0;j<500;j++)fx_launch_debug_log("bounded repeated error %u-%u abcdefghijklmnopqrstuvwxyz",i,j);
        fx_debug_file_tick();
    }
    assert(!fx_debug_file_ready);struct stat st;assert(!stat(current,&st)&&st.st_size<=FX_DEBUG_FILE_LIMIT);
    read_log(current);assert(strstr(text,"session log limit reached"));
    fx_debug_file_begin(0);unsigned calls=io_calls;before=writes;
    assert(fx_debug_file_prepare((void *)1));fx_debug_file_tick();fx_debug_file_exit();
    assert(io_calls==calls&&writes==before);
    puts("Debug file: quiet mode has no I/O; startup backlog, handoff errors, idle, rotation, contention bounds, full-card failure and 4-MiB cap passed.");
    return 0;
}
