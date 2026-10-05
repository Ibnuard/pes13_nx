#include <assert.h>
#include <setjmp.h>
#include <stdio.h>
#include <unistd.h>
#include <errno.h>
static int fault_at,crash_at,renames,sync_fault,syncs;
static jmp_buf crash;
static int mock_rename(const char *a,const char *b) {
    int n=++renames;
    if(n==fault_at){errno=EIO;return -1;}
    /* Match Horizon, not POSIX overwrite semantics. */
    if(!access(b,F_OK)){errno=EEXIST;return -1;}
    int rc=rename(a,b);
    if(!rc&&n==crash_at)longjmp(crash,1);
    return rc;
}
static int mock_fsync(int fd) {if(++syncs==sync_fault){errno=ENOSPC;return -1;}return fsync(fd);}
#define rename mock_rename
#define fsync mock_fsync
#include "../src/runtime/fextendo_presets.h"
#undef rename
#undef fsync
int main(int argc,char **argv){
    unsigned char before[5][4096],after[4096];size_t size[5];char path[1024];int i,n,mode;
    assert(argc==2);assert(fx_apply_preset(argv[1],0));
    /* Verify an unchanged launch performs no transaction writes or renames. */
    syncs=renames=0;assert(fx_apply_preset(argv[1],0));assert(!syncs&&!renames);
    for(i=0;i<5;i++){snprintf(path,sizeof(path),"%s%s",argv[1],fx_targets[i]);size[i]=fx_read(path,before[i],4096);assert(size[i]);}
    for(mode=0;mode<3;mode++)for(n=1;n<=(mode==2?6:11);n++){
        fault_at=crash_at=sync_fault=renames=syncs=0;
        if(mode==0)fault_at=n;else if(mode==1)crash_at=n;else sync_fault=n;
        if(!setjmp(crash))assert(!fx_apply_preset(argv[1],3));
        fault_at=crash_at=sync_fault=0;assert(fx_recover(argv[1]));
        for(i=0;i<5;i++){
            snprintf(path,sizeof(path),"%s%s",argv[1],fx_targets[i]);
            assert(fx_read(path,after,4096)==size[i]);assert(!memcmp(before[i],after,size[i]));
        }
    }
    /* Corrupt templates cannot change the installed preset. */
    snprintf(path,sizeof(path),"%s/launcher/presets/high-720.dat",argv[1]);
    assert(fx_write(path,"bad",3));assert(!fx_apply_preset(argv[1],3));
    puts("28 injected write/rename failures and power-loss points recovered; corrupt preset rejected.");
    return 0;
}
