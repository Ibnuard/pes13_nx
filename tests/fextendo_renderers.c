/* Real filesystem rollback, interrupted process and preset/renderer interaction. */
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <sys/wait.h>
#include <unistd.h>
static int fail_rename,crash_rename,rename_count,fail_sync,sync_count;
static int test_rename(const char *a,const char *b){
    int n=++rename_count;
    if(n==fail_rename){errno=EIO;return -1;}
    int result=rename(a,b);
    if(n==crash_rename){assert(!result);_exit(17);}
    return result;
}
static int test_sync(int fd){
    if(++sync_count==fail_sync){errno=ENOSPC;return -1;}
    return fsync(fd);
}
#define rename test_rename
#define fsync test_sync
#include "../src/runtime/fextendo_presets.h"
#include "../src/runtime/fextendo_renderers.h"
#undef rename
#undef fsync
static void reset(void){fail_rename=crash_rename=rename_count=fail_sync=sync_count=0;}
static void check(const char *root,int selected){
    char src[768],dst[768],b[2];
    for(int i=0;i<4;i++){
        snprintf(src,sizeof(src),"%s/launcher/renderers/%s/%s",root,fx_renderer_ids[selected],i<2?"d3d9.dll":"dxvk.conf");
        snprintf(dst,sizeof(dst),"%s%s",root,fx_renderer_targets[i]);assert(fx_files_equal(src,dst));
    }
    snprintf(dst,sizeof(dst),"%s%s",root,fx_renderer_targets[4]);assert(fx_read(dst,b,2)==2&&b[0]=='0'+selected&&b[1]=='\n');
}
int main(int argc,char **argv){
    assert(argc==2);const char *root=argv[1];char p[768],bad[800];
    assert(!fx_renderer_selected(root));assert(!fx_apply_renderer(root,-1));assert(!fx_apply_renderer(root,2));
    assert(fx_apply_renderer(root,0));check(root,0);
    reset();assert(fx_apply_renderer(root,0));assert(!rename_count&&!sync_count);
    /* Preference selection is cheap; installation waits until Play. */
    assert(fx_renderer_save(root,1));assert(fx_renderer_selected(root)==1);check(root,0);
    for(int n=1;n<=11;n++){
        reset();fail_rename=n;assert(!fx_apply_renderer(root,1));reset();assert(fx_renderer_recover(root));check(root,0);
    }
    for(int n=1;n<=6;n++){
        reset();fail_sync=n;assert(!fx_apply_renderer(root,1));reset();assert(fx_renderer_recover(root));check(root,0);
    }
    for(int n=1;n<=11;n++){
        pid_t child=fork();assert(child>=0);
        if(!child){reset();crash_rename=n;fx_apply_renderer(root,1);_exit(99);}
        int status;assert(waitpid(child,&status,0)==child&&WIFEXITED(status)&&WEXITSTATUS(status)==17);
        reset();assert(fx_renderer_recover(root));check(root,0);
    }
    assert(fx_apply_renderer(root,1));check(root,1);
    for(int preset=0;preset<4;preset++){assert(fx_apply_preset(root,preset));check(root,1);}
    assert(fx_apply_renderer(root,0));check(root,0);
    snprintf(p,sizeof(p),"%s/launcher/renderers/dxvk-2.7.1-async/d3d9.dll",root);
    snprintf(bad,sizeof(bad),"%s.test-backup",p);assert(!rename(p,bad));
    assert(fx_write(p,"MZ",2));assert(!fx_apply_renderer(root,1));check(root,0);
    assert(!unlink(p));assert(!fx_apply_renderer(root,1));check(root,0);assert(!rename(bad,p));
    /* A damaged journal blocks launch instead of accepting mixed DLLs. */
    snprintf(p,sizeof(p),"%s/launcher/renderer.txn",root);assert(fx_write(p,"!",1));
    assert(!fx_apply_renderer(root,1));assert(!unlink(p));
    assert(fx_renderer_save(root,0));
    puts("Renderer: 11 rename failures, 6 SD flush failures, 11 process interruptions, unchanged-file fast path, presets and missing/corrupt assets passed.");
}
