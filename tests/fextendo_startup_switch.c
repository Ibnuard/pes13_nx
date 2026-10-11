/* Real startup/cache state machine with modeled kernel and repair services. */
#include <assert.h>
#include <pthread.h>
#include "../src/runtime/fextendo_presets.h"
#include "../src/runtime/fextendo_renderers.h"
#include "../src/runtime/fextendo_ui.h"
#include "../src/runtime/fextendo_launch_memory.h"
#include "../src/runtime/fextendo_runtime_api.h"
static const char *root;
#define RUNTIME_DIR root
static struct fx_launch_memory fx_startup_memory;
static int kind,probes,checked,fx_ui_command,fx_ui_stop;
static pthread_mutex_t fx_ui_lock=PTHREAD_MUTEX_INITIALIZER;
static struct fx_view fx_ui_view;
static void fx_launch_memory_read(void){}
static int fxt_low_window_layout(uint64_t b,uint64_t s){return b==0x200000&&b+s==(1ull<<39);}
static int fxt_low_window_preflight(void){probes++;return kind!=3;}
static uint64_t armGetSystemTick(void){return 1;}
static uint64_t armTicksToNs(uint64_t n){return n;}
int fx_runtime_recover(struct fxr_job *j){(void)j;return 1;}
int fx_runtime_check(struct fxr_job *j){
    checked++;j->progress(FXR_CHECK,1,1,"");j->changed=0;
    if(kind==4){snprintf(j->error,sizeof(j->error),"Repair error");return 0;}
    if(kind==5){fx_ui_command=-1;return 0;}return 1;
}
int fx_runtime_repair(struct fxr_job *j){(void)j;abort();}
unsigned fx_runtime_file_count(void){return 1;}
static const char *catalog="test-catalog-v1";
const char *fx_runtime_catalog_id(void){return catalog;}
#include "../src/runtime/fextendo_startup_switch.h"
static void rerun(int force){
    fx_art_free(&fx_check_art);fx_check_request(force);fx_ui_command=0;fx_startup_switch();
}
int main(int argc,char **argv){
    assert(argc==3);root=argv[1];kind=atoi(argv[2]);
    fx_startup_memory=(struct fx_launch_memory){.base=kind==1?0x8000000:0x200000,
        .size=(kind==0?(1ull<<32):(1ull<<39))-(kind==1?0x8000000:0x200000)};
    assert(fx_startup_cache_clear(root));rerun(0);
    assert(fx_ui_view.check.visible);
    if(kind==0)assert(fx_boot_launch_ready&&!fx_boot_patch_active&&!probes);
    if(kind==1)assert(!fx_boot_launch_ready&&!fx_boot_patch_active&&!probes);
    if(kind==2)assert(fx_boot_launch_ready&&fx_boot_patch_active&&probes==1);
    if(kind==3)assert(!fx_boot_launch_ready&&!fx_boot_patch_active&&probes==1);
    if(kind==4)assert(fx_ui_view.check.failed&&!fx_ui_view.check.complete&&checked==1&&!fx_startup_cache_valid(root));
    else if(kind==5)assert(!fx_ui_view.check.complete&&!fx_check_art.font&&!fx_startup_cache_valid(root));
    else assert(fx_ui_view.check.complete);
    if(kind==6){
        char p[1024];struct stat st;
        /* Build representative immutable anchor files; no actual DLL needed. */
        for(unsigned i=2;i<5;i++){
            assert(fx_install_path(p,sizeof(p),root,fx_cache_anchors[i]));
            assert(fx_mkdir_parents(p));assert(fx_write(p,"runtime-test",12));
        }
        assert(fx_startup_cache_save(root)&&fx_startup_cache_valid(root));
        snprintf(p,sizeof(p),"%s/launcher/startup-verified.dat",root);assert(!stat(p,&st));time_t stamp=st.st_mtime;
        rerun(0);assert(fx_ui_view.check.complete&&fx_ui_view.check.cached&&checked==1);
        assert(!stat(p,&st)&&st.st_mtime==stamp); /* cached launch never rewrites */
        fx_startup_memory.base=0x8000000;fx_startup_memory.size=(1ull<<39)-0x8000000;
        rerun(0);assert(fx_ui_view.check.cached&&!fx_boot_launch_ready&&!fx_boot_patch_active&&checked==1);
        catalog="test-catalog-v2";assert(!fx_startup_cache_valid(root));rerun(0);assert(checked==2);
        kind=4;rerun(1);assert(checked==3&&fx_ui_view.check.failed&&!fx_startup_cache_valid(root));
        kind=6;rerun(1);assert(checked==4&&fx_ui_view.check.complete&&fx_startup_cache_valid(root));
        snprintf(p,sizeof(p),"%s/.runtime-fixer/plan",root);assert(fx_mkdir_parents(p));assert(fx_write(p,"pending",7));
        assert(!fx_startup_cache_valid(root));assert(!unlink(p));assert(fx_startup_cache_valid(root));
        snprintf(p,sizeof(p),"%s/drive_c/windows/system32/ntdll.dll",root);assert(fx_write(p,"changed-length",14));
        assert(!fx_startup_cache_valid(root));assert(fx_startup_cache_save(root));
        snprintf(p,sizeof(p),"%s/launcher/startup-verified.dat",root);assert(fx_write(p,"partial",7));
        assert(!fx_startup_cache_valid(root));
    }
    fx_art_free(&fx_check_art);assert(fx_startup_cache_clear(root));
    puts("PASS: GUI startup, per-boot admission, cache invalidation/force/recovery/cancel");return 0;
}
