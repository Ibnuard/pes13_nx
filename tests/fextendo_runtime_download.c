/* Optional live test against the same pinned GitHub asset as the NRO. */
#include <assert.h>
#include "../src/runtime/fextendo_runtime_download.h"
static int cancel_flag;
static int cancelled(void){return cancel_flag;}
int main(int argc,char **argv){
    assert(argc==2);struct fxr_job j={.root=argv[1],.cancelled=cancelled};
    char p[1024];assert(fxr_path(p,sizeof(p),j.root,".runtime-fixer/package.part"));
    /* Hard limits cannot be defeated by a malformed write callback. */
    struct fxr_transfer t={.job=&j,.file=tmpfile(),.received=FXR_ARCHIVE_SIZE-1};
    assert(t.file);assert(fxr_receive("xx",1,2,&t)==0);assert(ftell(t.file)==0);
    assert(fxr_receive("x",SIZE_MAX,2,&t)==0);fclose(t.file);
    cancel_flag=1;assert(!fxr_download(&j,p));assert(fxr_exists(p)==0);
    cancel_flag=0;j.error[0]=0;
    if(!fxr_download(&j,p)){fprintf(stderr,"%s\n",j.error);return 1;}
    assert(fxr_matches(p,FXR_ARCHIVE_SIZE,FXR_ARCHIVE_SHA,&j));
    /* All catalogued members can be staged with the actual minizip API. */
    memset(j.flags,1,sizeof(j.flags));j.changed=FXR_COUNT;
    assert(fxr_stage(&j,p));assert(fxr_install(&j));
    assert(fxr_check(&j)&&j.changed==0);assert(fxr_remove(p));
    puts("PASS: HTTPS download, size limit, cancellation, SHA256, all 205 runtime files installed and checked.");
    return 0;
}
