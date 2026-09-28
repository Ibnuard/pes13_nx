/* LGPL-2.1-or-later. A single UI thread owns and releases its framebuffer.
 * The thread and artwork are gone before Wine acquires the 3D surface. */
#ifndef FEXTENDO_LAUNCHER_H
#define FEXTENDO_LAUNCHER_H
#include <pthread.h>

static pthread_t fx_ui_thread;
static pthread_mutex_t fx_ui_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t fx_handoff_lock=PTHREAD_MUTEX_INITIALIZER;
static int fx_ui_created,fx_ui_owned,fx_ui_stop,fx_ui_command,fx_boot_started,fx_first_present;
static struct fx_view fx_ui_view={.screen=FX_HOME};
static char fx_ui_message[192];
static void fx_native_error(const char *message) {
    ErrorApplicationConfig c;
    if(R_SUCCEEDED(errorApplicationCreate(&c,message,"Fextendo could not start PES13. Check fex-runtime.log, then close and relaunch.")))
        errorApplicationShow(&c);
}
static void fx_fail(const char *message) {
    if(!__atomic_load_n(&fx_boot_started,__ATOMIC_ACQUIRE)||__atomic_load_n(&fx_first_present,__ATOMIC_ACQUIRE))return;
    pthread_mutex_lock(&fx_ui_lock);
    if(__atomic_load_n(&fx_ui_owned,__ATOMIC_ACQUIRE)){
        snprintf(fx_ui_message,sizeof(fx_ui_message),"%s",message);
        fx_ui_view.message=fx_ui_message;fx_ui_view.screen=FX_FAILED;fx_ui_view.fatal=1;
        pthread_mutex_unlock(&fx_ui_lock);
    }else{pthread_mutex_unlock(&fx_ui_lock);fx_native_error(message);}
}
static void fx_exit_check(void) {
    if(__atomic_load_n(&fx_boot_started,__ATOMIC_ACQUIRE)&&!__atomic_load_n(&fx_first_present,__ATOMIC_ACQUIRE))
        fx_native_error("Launch failed. PES13 exited before its first frame.");
}
static int fx_owned(void) {return __atomic_load_n(&fx_ui_owned,__ATOMIC_ACQUIRE);}
static int fx_handoff(void) {
    int failed;
    pthread_mutex_lock(&fx_handoff_lock);
    pthread_mutex_lock(&fx_ui_lock);failed=fx_ui_view.screen==FX_FAILED;
    pthread_mutex_unlock(&fx_ui_lock);
    if(!failed && fx_ui_created){
        __atomic_store_n(&fx_ui_stop,1,__ATOMIC_RELEASE);
        pthread_join(fx_ui_thread,NULL);fx_ui_created=0;
        log_line("[FEXTENDO] launcher stopped and framebuffer released before 3D handoff");
        fx_timestamp_start();
    }
    pthread_mutex_unlock(&fx_handoff_lock);return !failed;
}
static void fx_stage(const char *text) {
    if(!fx_owned())return;
    pthread_mutex_lock(&fx_ui_lock);
    if(fx_ui_view.screen==FX_LOADING){snprintf(fx_ui_message,sizeof(fx_ui_message),"%s",text);fx_ui_view.message=fx_ui_message;}
    pthread_mutex_unlock(&fx_ui_lock);
}
static void *fx_ui_main(void *arg) {
    struct fx_art art;Framebuffer fb;PadState pad;Result rc;int pending=0,last_dir=0;u64 repeat=0,started=0;
    (void)arg;
    if(!fx_art_load(&art,RUNTIME_DIR)){
        fx_native_error("Launcher assets missing or damaged. Copy the complete switch folder.");
        __atomic_store_n(&fx_ui_command,-1,__ATOMIC_RELEASE);return NULL;
    }
    rc=framebufferCreate(&fb,nwindowGetDefault(),FX_W,FX_H,PIXEL_FORMAT_RGBA_8888,2);
    if(R_FAILED(rc))goto failed_fb;
    rc=framebufferMakeLinear(&fb);
    if(R_FAILED(rc)){framebufferClose(&fb);goto failed_fb;}
    padConfigureInput(1,HidNpadStyleSet_NpadStandard);padInitializeDefault(&pad);
    __atomic_store_n(&fx_ui_owned,1,__ATOMIC_RELEASE);
    if(!fx_recover(RUNTIME_DIR)){
        fx_ui_view.screen=FX_FAILED;fx_ui_view.fatal=1;
        fx_ui_view.message="Preset recovery failed. Check SD card space.";
    }
    fx_ui_view.selected=fx_selected(RUNTIME_DIR);
    fx_ui_view.timestamp=fx_debug_timestamp(RUNTIME_DIR);
    while(!__atomic_load_n(&fx_ui_stop,__ATOMIC_ACQUIRE)){
        u64 frame_start=armGetSystemTick(),down,held;int dir=0,confirm;
        if(!appletMainLoop()){
            __atomic_store_n(&fx_boot_started,0,__ATOMIC_RELEASE);
            __atomic_store_n(&fx_ui_command,-1,__ATOMIC_RELEASE);break;
        }
        padUpdate(&pad);down=padGetButtonsDown(&pad);held=padGetButtons(&pad);
        if(held&(HidNpadButton_Left|HidNpadButton_StickLLeft|HidNpadButton_Up|HidNpadButton_StickLUp))dir=-1;
        else if(held&(HidNpadButton_Right|HidNpadButton_StickLRight|HidNpadButton_Down|HidNpadButton_StickLDown))dir=1;
        if(dir!=last_dir){last_dir=dir;repeat=frame_start+armNsToTicks(300000000);}
        else if(dir&&frame_start>=repeat)repeat=frame_start+armNsToTicks(130000000);
        else dir=0;
        confirm=(down&HidNpadButton_A)!=0;
        pthread_mutex_lock(&fx_ui_lock);
        if(fx_ui_view.screen==FX_HOME||fx_ui_view.screen==FX_SETTINGS){
            if(down&HidNpadButton_Plus){
                __atomic_store_n(&fx_ui_command,-1,__ATOMIC_RELEASE);
                pthread_mutex_unlock(&fx_ui_lock);break;
            }
        }
        if(fx_ui_view.screen==FX_HOME){
            if(dir)fx_ui_view.tile=1-fx_ui_view.tile;
            if(down&HidNpadButton_B)fx_ui_view.tile=0;
            if(confirm&&fx_ui_view.tile){fx_ui_view.screen=FX_SETTINGS;fx_ui_view.row=fx_ui_view.selected;fx_ui_view.saved=0;}
            else if(confirm){
                FILE *game=fopen(DEFAULT_TARGET,"rb");
                if(!game){fx_ui_view.screen=FX_FAILED;fx_ui_view.fatal=0;fx_ui_view.message="PES13 was not found. Check the game folder.";}
                else{
                    fclose(game);
                    if(!fx_apply_preset(RUNTIME_DIR,fx_ui_view.selected)){
                        fx_ui_view.screen=FX_FAILED;fx_ui_view.fatal=0;fx_ui_view.message="Could not save the preset. Check the SD card.";
                    }else{
                        fx_timestamp_arm(fx_ui_view.timestamp,frame_start);
                        fx_ui_view.screen=FX_LOADING;fx_ui_view.message="Preparing your game...";pending=1;started=frame_start;
                    }
                }
            }
        }else if(fx_ui_view.screen==FX_SETTINGS){
            if(dir){fx_ui_view.row=(fx_ui_view.row+dir+5)%5;fx_ui_view.saved=0;}
            if(down&HidNpadButton_B)fx_ui_view.screen=FX_HOME;
            else if(confirm){
                if(fx_ui_view.row==4){
                    if(fx_debug_timestamp_save(RUNTIME_DIR,!fx_ui_view.timestamp)){fx_ui_view.timestamp=!fx_ui_view.timestamp;fx_ui_view.saved=1;}
                    else{fx_ui_view.screen=FX_FAILED;fx_ui_view.fatal=0;fx_ui_view.message="Could not save the timestamp setting. Check the SD card.";}
                }
                else if(fx_apply_preset(RUNTIME_DIR,fx_ui_view.row)){fx_ui_view.selected=fx_ui_view.row;fx_ui_view.saved=1;}
                else{fx_ui_view.screen=FX_FAILED;fx_ui_view.fatal=0;fx_ui_view.message="Could not save the preset. Check the SD card.";}
            }
        }else if(fx_ui_view.screen==FX_FAILED&&(confirm||(!fx_ui_view.fatal&&(down&HidNpadButton_B)))){
            if(fx_ui_view.fatal){
                __atomic_store_n(&fx_boot_started,0,__ATOMIC_RELEASE);
                __atomic_store_n(&fx_ui_command,-1,__ATOMIC_RELEASE);
                pthread_mutex_unlock(&fx_ui_lock);
                framebufferClose(&fb);fx_art_free(&art);__atomic_store_n(&fx_ui_owned,0,__ATOMIC_RELEASE);exit(0);
            }else fx_ui_view.screen=FX_HOME;
        }
        if(fx_ui_view.screen==FX_LOADING&&pending&&!(held&HidNpadButton_A)){
            pending=0;__atomic_store_n(&fx_boot_started,1,__ATOMIC_RELEASE);
            __atomic_store_n(&fx_ui_command,1,__ATOMIC_RELEASE);
        }
        if(fx_ui_view.screen==FX_LOADING&&started&&armTicksToNs(frame_start-started)>180000000000ull){
            fx_ui_view.screen=FX_FAILED;fx_ui_view.fatal=1;fx_ui_view.message="Startup timed out. Close and relaunch to retry.";
        }
        u32 stride;uint32_t *pixels=framebufferBegin(&fb,&stride);
        if(pixels){struct fx_canvas c={pixels,(int)stride/4,&art};fx_render(&c,&fx_ui_view);framebufferEnd(&fb);}
        fx_ui_view.frame++;pthread_mutex_unlock(&fx_ui_lock);
        u64 elapsed=armTicksToNs(armGetSystemTick()-frame_start);
        if(elapsed<33333333)svcSleepThread(33333333-elapsed);
    }
    framebufferClose(&fb);fx_art_free(&art);__atomic_store_n(&fx_ui_owned,0,__ATOMIC_RELEASE);return NULL;
failed_fb:
    fx_art_free(&art);fx_native_error("Launcher display initialization failed.");
    __atomic_store_n(&fx_ui_command,-1,__ATOMIC_RELEASE);return NULL;
}
static int fx_launcher_start(void) {
    int command,rc;pthread_attr_t attr;
    if(pthread_attr_init(&attr)){
        fx_native_error("Unable to prepare the launcher thread.");return 0;
    }
    /* Preset staging has bounded local buffers. Do not depend on the SDK's
     * default pthread stack size; all UI memory is released at handoff. */
    rc=pthread_attr_setstacksize(&attr,256*1024);
    if(!rc)rc=pthread_create(&fx_ui_thread,&attr,fx_ui_main,NULL);
    pthread_attr_destroy(&attr);
    if(rc){
        fx_native_error("Unable to start the launcher.");return 0;
    }
    fx_ui_created=1;
    while(!(command=__atomic_load_n(&fx_ui_command,__ATOMIC_ACQUIRE)))svcSleepThread(10000000);
    if(command<0){pthread_join(fx_ui_thread,NULL);fx_ui_created=0;return 0;}
    atexit(fx_exit_check);
    log_line("[FEXTENDO] launch requested; canonical settings=C:\\KONAMI\\Pro Evolution Soccer 2013\\settings.dat; VSync=on");
    return 1;
}
#endif
