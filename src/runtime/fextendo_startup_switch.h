/* SPDX-License-Identifier: LGPL-2.1-or-later. Main-thread startup work.
 * The launcher UI alone owns the framebuffer and controller input. */
#ifndef FEXTENDO_STARTUP_SWITCH_H
#define FEXTENDO_STARTUP_SWITCH_H
#include "fextendo_startup_check.h"
#include "fextendo_startup_cache.h"
static int fx_boot_patch_active,fx_boot_launch_ready,fx_check_force;
static uint64_t fx_check_tick;
static struct fx_art fx_check_art;
static int fx_check_poll(void){
    return __atomic_load_n(&fx_ui_command,__ATOMIC_ACQUIRE)<0||__atomic_load_n(&fx_ui_stop,__ATOMIC_ACQUIRE);
}
static void fx_check_progress(int phase,uint64_t current,uint64_t total,const char *name){
    (void)name;
    static const int stages[]={FX_CHECK_RUNTIME,FX_CHECK_DOWNLOAD,FX_CHECK_VERIFY,FX_CHECK_INSTALL,FX_CHECK_RECOVER};
    if(phase<FXR_CHECK||phase>FXR_RECOVER)return;
    uint64_t now=armGetSystemTick();
    pthread_mutex_lock(&fx_ui_lock);
    if(fx_ui_view.check.phase!=stages[phase]||current==total||!fx_check_tick||armTicksToNs(now-fx_check_tick)>=100000000ull){
        fx_check_tick=now;fx_ui_view.check.game_done=1;fx_ui_view.check.phase=stages[phase];
        fx_ui_view.check.percent=total?(int)((current>total?total:current)*100/total):-1;
    }
    pthread_mutex_unlock(&fx_ui_lock);
}
static void fx_check_request(int force){ /* Called with the UI lock. */
    fx_check_force=force;
    fx_ui_view.check=(struct fx_check_view){.visible=1,.phase=FX_CHECK_BOOT,.percent=-1};
    __atomic_store_n(&fx_ui_command,2,__ATOMIC_RELEASE);
}
static void fx_startup_switch(void){
    fx_check_tick=0;
    struct fxr_job job={.root=RUNTIME_DIR,.progress=fx_check_progress,.cancelled=fx_check_poll};
    fx_launch_memory_read();
    int mode=fx_memory_mode(&fx_startup_memory);
    /* A cached PASS never grants memory admission or High on a new boot. */
    fx_boot_patch_active=mode==FX_MEMORY_39&&
        fxt_low_window_layout(fx_startup_memory.base,fx_startup_memory.size)&&fxt_low_window_preflight();
    fx_boot_launch_ready=mode==FX_MEMORY_32_NO_ALIAS||fx_boot_patch_active;
    int cached=!fx_check_force&&fx_startup_cache_valid(RUNTIME_DIR);
    pthread_mutex_lock(&fx_ui_lock);
    fx_ui_view.boot_patch=fx_boot_patch_active;fx_ui_view.check.memory_done=1;
    fx_ui_view.check.phase=FX_CHECK_GAME;fx_ui_view.check.cached=cached;
    pthread_mutex_unlock(&fx_ui_lock);
    int ok=1;
    if(!cached){
        if(!fx_startup_cache_clear(RUNTIME_DIR)){
            snprintf(job.error,sizeof(job.error),"Could not reset the saved check. Check SD card access.");ok=0;
        }
        if(ok)ok=fx_startup_check(&job);
    }
    if(ok&&!fx_check_poll()){
        pthread_mutex_lock(&fx_ui_lock);
        fx_ui_view.check.game_done=fx_ui_view.check.runtime_done=1;
        fx_ui_view.check.phase=FX_CHECK_ART;fx_ui_view.check.percent=-1;
        pthread_mutex_unlock(&fx_ui_lock);
        ok=fx_art_load(&fx_check_art,RUNTIME_DIR);
        if(!ok){
            fx_startup_cache_clear(RUNTIME_DIR);
            snprintf(job.error,sizeof(job.error),"Could not load launcher artwork. Retry to check and repair the runtime.");
        }else if(!cached&&!fx_check_poll()){
            /* A read-only/full SD cannot poison the receipt. The successful
             * session may continue, but next launch must check again. */
            fx_startup_cache_save(RUNTIME_DIR);
        }
    }
    pthread_mutex_lock(&fx_ui_lock);
    if(fx_check_poll())fx_art_free(&fx_check_art);
    else if(ok)fx_ui_view.check.complete=1;
    else{
        fx_ui_view.check.failed=1;
        snprintf(fx_ui_view.check.error,sizeof(fx_ui_view.check.error),"%s",job.error);
    }
    pthread_mutex_unlock(&fx_ui_lock);
}
#endif
