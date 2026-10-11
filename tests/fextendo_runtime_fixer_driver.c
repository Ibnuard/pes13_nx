/* Exercise the same installer used by the Switch launcher, with real files. */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <sys/stat.h>
static int step,fail_at,crash_at;
static int fault(void){step++;if(step==fail_at){errno=EIO;return 1;}return 0;}
static void after(void){if(step==crash_at)_exit(77);}
static int test_rename(const char *a,const char *b){if(fault())return -1;int r=rename(a,b);after();return r;}
static int test_unlink(const char *a){if(fault())return -1;int r=unlink(a);after();return r;}
static int test_sync(void){if(fault())return 0;after();return 1;}
static size_t test_write(const void *p,size_t a,size_t b,FILE *f){if(fault())return 0;size_t n=fwrite(p,a,b,f);after();return n;}
#define FXR_RENAME test_rename
#define FXR_UNLINK test_unlink
#define FXR_SYNC test_sync
#define fwrite test_write
#define FXR_TEST_CATALOG
struct fxr_file;
#include "fixture_catalog.h"
#include "../src/runtime/fextendo_runtime_fixer.h"
static int cancel_phase=-1,current_phase=-2;
static void progress(int phase,uint64_t n,uint64_t total,const char *s){(void)n;(void)total;(void)s;current_phase=phase;}
static int cancelled(void){return cancel_phase==current_phase;}
int main(int argc,char **argv){
    if(argc!=7)return 2;
    fail_at=atoi(argv[4]);crash_at=atoi(argv[5]);cancel_phase=atoi(argv[6]);
    struct fxr_job j={.root=argv[1],.progress=progress,.cancelled=cancelled};
    int ok=fxr_recover(&j);
    if(ok&&!strcmp(argv[3],"check"))ok=fxr_check(&j);
    if(ok&&!strcmp(argv[3],"repair"))ok=fxr_check(&j)&&fxr_stage(&j,argv[2])&&fxr_install(&j);
    printf("ok=%d changed=%u steps=%d error=%s\n",ok,j.changed,step,j.error);
    return ok?0:1;
}
