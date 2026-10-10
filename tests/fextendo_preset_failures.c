#include <assert.h>
#include <setjmp.h>
#include <stdio.h>
#include <unistd.h>
#include <errno.h>
static int fault_at,crash_at,renames,sync_fault,syncs,corrupt_sync;
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
static int mock_fsync(int fd) {
    if(++syncs==sync_fault){errno=ENOSPC;return -1;}
    int rc=fsync(fd);
    if(!rc&&syncs==corrupt_sync)assert(pwrite(fd,"X",1,0)==1);
    return rc;
}
#define rename mock_rename
#define fsync mock_fsync
#include "../src/runtime/fextendo_presets.h"
#undef rename
#undef fsync
int main(int argc,char **argv){
    unsigned char before[5][4096],after[4096];size_t size[5];char path[1024];int i,n,mode;
    assert(argc==2);assert(fx_apply_preset(argv[1],0));
    /* A valid imported canonical profile enables frame skipping and has
     * custom input mappings and neither XInput selection bit. Every preset
     * clears frame skipping, enables both XInput bits, preserves controls and
     * other flags, and produces three valid identical files. */
    unsigned char imported[852],expected[852];unsigned flags;
    snprintf(path,sizeof(path),"%s%s",argv[1],fx_targets[0]);
    assert(fx_read(path,imported,sizeof(imported))==852);
    imported[14]=0xf6;imported[15]=0xfd;
    for(i=32;i<852;i++)imported[i]=(unsigned char)(i*37+11);
    uint16_t crc=fx_crc(imported);imported[12]=crc;imported[13]=crc>>8;
    assert(fx_valid_settings(imported,852));
    for(int preset=0;preset<4;preset++){
        snprintf(path,sizeof(path),"%s%s",argv[1],fx_targets[0]);
        assert(fx_write(path,imported,852));assert(fx_apply_preset(argv[1],preset));
        for(i=0;i<3;i++){
            snprintf(path,sizeof(path),"%s%s",argv[1],fx_targets[i]);
            assert(fx_read(path,after,sizeof(after))==852&&fx_valid_settings(after,852));
            assert(fx_settings_flags(argv[1],i,&flags)&&flags==0xfffd);
            assert(!memcmp(after,imported,12)&&!memcmp(after+32,imported+32,820));
            if(!i)memcpy(expected,after,852);else assert(!memcmp(expected,after,852));
        }
        syncs=renames=0;assert(fx_apply_preset(argv[1],preset));assert(!syncs&&!renames);
    }
    /* Readback rejects corruption even if the flag bytes look right. */
    expected[50]^=1;assert(fx_write(path,expected,852));
    assert(!fx_verify_settings_flags(argv[1]));
    assert(fx_apply_preset(argv[1],0));assert(fx_verify_settings_flags(argv[1]));
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
    /* A successful write call with bad persisted content must not commit. */
    syncs=renames=0;corrupt_sync=3;assert(!fx_apply_preset(argv[1],3));corrupt_sync=0;
    assert(fx_recover(argv[1]));
    for(i=0;i<5;i++){
        snprintf(path,sizeof(path),"%s%s",argv[1],fx_targets[i]);
        assert(fx_read(path,after,4096)==size[i]&&!memcmp(before[i],after,size[i]));
    }
    /* Corrupt templates cannot change the installed preset. */
    snprintf(path,sizeof(path),"%s/launcher/presets/high-720.dat",argv[1]);
    assert(fx_write(path,"bad",3));assert(!fx_apply_preset(argv[1],3));
    puts("All four presets clear imported frame skipping in three CRC-valid files, preserve bindings/other flags and avoid repeat writes; 28 transaction failures plus corrupted write recovered; corrupt data rejected.");
    return 0;
}
