/* LGPL-2.1-or-later. A single UI thread owns and releases its framebuffer.
 * The thread and artwork are gone before Wine acquires the 3D surface. */
#ifndef FEXTENDO_LAUNCHER_H
#define FEXTENDO_LAUNCHER_H
#include <pthread.h>
#ifndef FX_SPLASH_MS
#define FX_SPLASH_MS 2400
#endif
#define FX_UI_FRAME_NS 16666667ull

static pthread_t fx_ui_thread;
static pthread_mutex_t fx_ui_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t fx_handoff_lock=PTHREAD_MUTEX_INITIALIZER;
static int fx_ui_created,fx_ui_owned,fx_ui_stop,fx_ui_command,fx_boot_started,fx_first_present;
static struct fx_view fx_ui_view={.screen=FX_HOME,.sound=1,.battery=-1};
#ifdef WINE_NX_LSFG
extern int wine_nx_lsfg_available(void);
extern const char *wine_nx_lsfg_unavailable_reason(void);
extern void wine_nx_lsfg_configure(int enabled,int performance,int flow);
#endif
static int fx_frame_generation_available(void) {
#ifdef WINE_NX_LSFG
    return wine_nx_lsfg_available();
#else
    return 0;
#endif
}
static const char *fx_frame_generation_unavailable_reason(void) {
#ifdef WINE_NX_LSFG
    return wine_nx_lsfg_unavailable_reason();
#else
    return "This build does not include frame generation.";
#endif
}
static char fx_ui_message[192];
static uint64_t fx_history_tick;
static int fx_history_written;
static void fx_record_first_present(void) {
    if(!__atomic_load_n(&fx_first_present,__ATOMIC_ACQUIRE)&&
       !__atomic_exchange_n(&fx_first_present,1,__ATOMIC_ACQ_REL))
        __atomic_store_n(&fx_history_tick,armGetSystemTick(),__ATOMIC_RELEASE);
}
static void fx_history_flush(void) {
    uint64_t tick=__atomic_load_n(&fx_history_tick,__ATOMIC_ACQUIRE);
    if(!tick||__atomic_load_n(&fx_history_written,__ATOMIC_ACQUIRE))return;
    time_t now=time(NULL);uint64_t current=armGetSystemTick();
    uint64_t elapsed=current>=tick?armTicksToNs(current-tick)/1000000000ull:0;
    if(now<=0||(uint64_t)now<946684800ull+elapsed)return;
    if(__atomic_exchange_n(&fx_history_written,1,__ATOMIC_ACQ_REL))return;
    /* Existing log flusher (or exit) owns SD I/O; Present only stores a tick. */
    if(!fx_last_played_save(RUNTIME_DIR,(uint64_t)now-elapsed))
        log_line("[FEXTENDO] last-played history could not be saved");
}
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
    fx_history_flush();
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
    struct fx_art art;Framebuffer fb;PadState pad;Result rc;int pending=0,last_dir=0,psm_ready=0,splash_done=0;u64 repeat=0,started=0,last_frame=0,battery_due=0,ui_origin=0;
    u64 render_sum=0,render_max=0,render_frames=0;
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
    if(!fx_renderer_recover(RUNTIME_DIR)||!fx_recover(RUNTIME_DIR)){
        fx_ui_view.screen=FX_FAILED;fx_ui_view.fatal=1;
        fx_ui_view.message="Settings recovery failed. Check SD card space.";
    }
    fx_ui_view.selected=fx_selected(RUNTIME_DIR);
    fx_ui_view.renderer=fx_renderer_selected(RUNTIME_DIR);
    fx_ui_view.frame_generation=fx_frame_generation(RUNTIME_DIR)&&fx_frame_generation_available();
    fx_ui_view.timestamp=fx_debug_timestamp(RUNTIME_DIR);
    fx_ui_view.last_played=fx_last_played(RUNTIME_DIR);
    fx_ui_view.sound=fx_menu_sound(RUNTIME_DIR);
    fx_ui_view.music=fx_background_music(RUNTIME_DIR);fx_music_set(fx_ui_view.music);fx_sfx_init(RUNTIME_DIR);
    psm_ready=R_SUCCEEDED(psmInitialize());
    ui_origin=armGetSystemTick();
    while(!__atomic_load_n(&fx_ui_stop,__ATOMIC_ACQUIRE)){
        u64 frame_start=armGetSystemTick(),down,held;int dir=0,confirm;
        if(!appletMainLoop()){
            __atomic_store_n(&fx_boot_started,0,__ATOMIC_RELEASE);
            __atomic_store_n(&fx_ui_command,-1,__ATOMIC_RELEASE);break;
        }
        padUpdate(&pad);down=padGetButtonsDown(&pad);held=padGetButtons(&pad);
        if(!splash_done&&fx_ui_view.screen==FX_HOME){
            u64 elapsed_ms=armTicksToNs(frame_start-ui_origin)/1000000;
            if(elapsed_ms>=FX_SPLASH_MS)splash_done=1;
            else if(down){splash_done=1;down&=HidNpadButton_Plus;held=0;}
            fx_ui_view.splash_ms=splash_done?0:FX_SPLASH_MS-(unsigned)elapsed_ms;
        }
        if(held&(HidNpadButton_Left|HidNpadButton_StickLLeft|HidNpadButton_Up|HidNpadButton_StickLUp))dir=-1;
        else if(held&(HidNpadButton_Right|HidNpadButton_StickLRight|HidNpadButton_Down|HidNpadButton_StickLDown))dir=1;
        if(dir!=last_dir){last_dir=dir;repeat=frame_start+armNsToTicks(300000000);}
        else if(dir&&frame_start>=repeat)repeat=frame_start+armNsToTicks(130000000);
        else dir=0;
        if(frame_start>=battery_due){
            time_t now=time(NULL);fx_ui_view.wall_time=now>0?(uint64_t)now:0;
            if(psm_ready){
            u32 percent;PsmChargerType charger;
            fx_ui_view.battery=R_SUCCEEDED(psmGetBatteryChargePercentage(&percent))?(int)(percent>100?100:percent):-1;
            fx_ui_view.charging=R_SUCCEEDED(psmGetChargerType(&charger))&&charger!=PsmChargerType_Unconnected;
            }
            battery_due=frame_start+armNsToTicks(10000000000ull);
        }
        confirm=(down&HidNpadButton_A)!=0;
        pthread_mutex_lock(&fx_ui_lock);
        int old_tile=fx_ui_view.tile,old_row=fx_ui_view.row,old_page=fx_ui_view.credit_page;
        if(fx_ui_view.screen==FX_HOME||fx_ui_view.screen==FX_SETTINGS||fx_ui_view.screen==FX_CREDITS){
            if(down&HidNpadButton_Plus){
                __atomic_store_n(&fx_ui_command,-1,__ATOMIC_RELEASE);
                pthread_mutex_unlock(&fx_ui_lock);break;
            }
        }
        if(fx_ui_view.screen==FX_HOME){
            if(dir)fx_ui_view.tile=(fx_ui_view.tile+dir+3)%3;
            if(down&HidNpadButton_B)fx_ui_view.tile=0;
            if(confirm&&fx_ui_view.tile==2){fx_ui_view.screen=FX_CREDITS;fx_ui_view.credit_page=0;}
            else if(confirm&&fx_ui_view.tile==1){fx_ui_view.screen=FX_SETTINGS;fx_ui_view.row=fx_ui_view.selected;fx_ui_view.settings_scroll=fx_settings_scroll_target(fx_ui_view.row);fx_ui_view.saved=0;}
            else if(confirm){
                FILE *game=fopen(DEFAULT_TARGET,"rb");
                if(!game){fx_ui_view.screen=FX_FAILED;fx_ui_view.fatal=0;fx_ui_view.message="PES13 was not found. Check the game folder.";}
                else{
                    fclose(game);
                    fx_timestamp_arm(fx_ui_view.timestamp,frame_start);
                    fx_ui_view.screen=FX_LOADING;fx_ui_view.message="Preparing your game...";pending=1;started=frame_start;
                }
            }
        }else if(fx_ui_view.screen==FX_SETTINGS){
            if(dir){fx_ui_view.row=(fx_ui_view.row+dir+FX_SETTINGS_ROWS)%FX_SETTINGS_ROWS;fx_ui_view.saved=0;}
            if(down&HidNpadButton_B)fx_ui_view.screen=FX_HOME;
            else if(confirm){
                if(fx_ui_view.row==9){
                    if(!fx_ui_view.frame_generation&&!fx_lossless_available(RUNTIME_DIR)){
                        fx_ui_view.screen=FX_FAILED;fx_ui_view.fatal=0;
                        fx_ui_view.message="Copy your Lossless.dll to switch/pes13-fex/lsfg first.";
                    }else if(!fx_ui_view.frame_generation&&!fx_frame_generation_available()){
                        fx_ui_view.screen=FX_FAILED;fx_ui_view.fatal=0;
                        fx_ui_view.message=fx_frame_generation_unavailable_reason();
                        log_line("[LSFG] not enabled: %s",fx_ui_view.message);
                    }else if(fx_frame_generation_save(RUNTIME_DIR,!fx_ui_view.frame_generation)){
                        fx_ui_view.frame_generation=!fx_ui_view.frame_generation;fx_ui_view.saved=1;
                    }else{fx_ui_view.screen=FX_FAILED;fx_ui_view.fatal=0;fx_ui_view.message="Could not save frame generation. Check the SD card.";}
                }
                else if(fx_ui_view.row>=7){
                    int selected=fx_ui_view.row-7;
                    if(fx_renderer_save(RUNTIME_DIR,selected)){fx_ui_view.renderer=selected;fx_ui_view.saved=1;}
                    else{fx_ui_view.screen=FX_FAILED;fx_ui_view.fatal=0;fx_ui_view.message="Could not save the renderer. Check the SD card.";}
                }
                else if(fx_ui_view.row==6){
                    if(fx_background_music_save(RUNTIME_DIR,!fx_ui_view.music)){fx_ui_view.music=!fx_ui_view.music;fx_music_set(fx_ui_view.music);fx_ui_view.saved=1;}
                    else{fx_ui_view.screen=FX_FAILED;fx_ui_view.fatal=0;fx_ui_view.message="Could not save the music setting. Check the SD card.";}
                }
                else if(fx_ui_view.row==5){
                    if(fx_menu_sound_save(RUNTIME_DIR,!fx_ui_view.sound)){fx_ui_view.sound=!fx_ui_view.sound;fx_ui_view.saved=1;}
                    else{fx_ui_view.screen=FX_FAILED;fx_ui_view.fatal=0;fx_ui_view.message="Could not save the sound setting. Check the SD card.";}
                }
                else if(fx_ui_view.row==4){
                    if(fx_debug_timestamp_save(RUNTIME_DIR,!fx_ui_view.timestamp)){fx_ui_view.timestamp=!fx_ui_view.timestamp;fx_ui_view.saved=1;}
                    else{fx_ui_view.screen=FX_FAILED;fx_ui_view.fatal=0;fx_ui_view.message="Could not save the timestamp setting. Check the SD card.";}
                }
                else if(fx_apply_preset(RUNTIME_DIR,fx_ui_view.row)){fx_ui_view.selected=fx_ui_view.row;fx_ui_view.saved=1;}
                else{fx_ui_view.screen=FX_FAILED;fx_ui_view.fatal=0;fx_ui_view.message="Could not save the preset. Check the SD card.";}
            }
        }else if(fx_ui_view.screen==FX_CREDITS){
            if(down&HidNpadButton_B)fx_ui_view.screen=FX_HOME;
            else if(dir||(down&(HidNpadButton_L|HidNpadButton_R)))fx_ui_view.credit_page=1-fx_ui_view.credit_page;
        }else if(fx_ui_view.screen==FX_FAILED&&(confirm||(!fx_ui_view.fatal&&(down&HidNpadButton_B)))){
            if(fx_ui_view.fatal){
                __atomic_store_n(&fx_boot_started,0,__ATOMIC_RELEASE);
                __atomic_store_n(&fx_ui_command,-1,__ATOMIC_RELEASE);
                pthread_mutex_unlock(&fx_ui_lock);
                fx_sfx_close();if(psm_ready)psmExit();
                framebufferClose(&fb);fx_art_free(&art);__atomic_store_n(&fx_ui_owned,0,__ATOMIC_RELEASE);exit(0);
            }else fx_ui_view.screen=FX_HOME;
        }
        if(confirm)fx_sfx_play(fx_ui_view.screen==FX_FAILED?FX_ERROR:FX_CONFIRM,fx_ui_view.sound);
        else if(down&HidNpadButton_B)fx_sfx_play(FX_BACK,fx_ui_view.sound);
        else if(fx_ui_view.tile!=old_tile||fx_ui_view.row!=old_row||fx_ui_view.credit_page!=old_page)fx_sfx_play(FX_NAV,fx_ui_view.sound);
        if(fx_ui_view.screen==FX_LOADING&&pending&&!(held&HidNpadButton_A)&&armTicksToNs(frame_start-started)>=120000000){
            fx_sfx_close(); /* never overlap the game's audout session */
            pending=0;__atomic_store_n(&fx_boot_started,1,__ATOMIC_RELEASE);
            __atomic_store_n(&fx_ui_command,1,__ATOMIC_RELEASE);
        }
        if(fx_ui_view.screen==FX_LOADING&&started&&armTicksToNs(frame_start-started)>180000000000ull){
            fx_ui_view.screen=FX_FAILED;fx_ui_view.fatal=1;fx_ui_view.message="Startup timed out. Close and relaunch to retry.";
        }
        fx_motion_step(&fx_ui_view,last_frame?armTicksToNs(frame_start-last_frame)/1000000.f:33.f);
        last_frame=frame_start;fx_ui_view.frame=(unsigned)(armTicksToNs(frame_start-ui_origin)/33333333);
        u64 render_start=armGetSystemTick();
        u32 stride;uint32_t *pixels=framebufferBegin(&fb,&stride);
        if(pixels){struct fx_canvas c={pixels,(int)stride/4,&art};fx_render(&c,&fx_ui_view);framebufferEnd(&fb);}
        u64 render_ns=armTicksToNs(armGetSystemTick()-render_start);
        render_sum+=render_ns;render_frames++;if(render_ns>render_max)render_max=render_ns;
        pthread_mutex_unlock(&fx_ui_lock);
        u64 elapsed=armTicksToNs(armGetSystemTick()-frame_start);
        if(elapsed<FX_UI_FRAME_NS)svcSleepThread(FX_UI_FRAME_NS-elapsed);
    }
    if(render_frames)log_line("[FEXTENDO] menu frames=%llu mean_draw_present_us=%llu max_draw_present_us=%llu target_hz=60",
        (unsigned long long)render_frames,(unsigned long long)(render_sum/render_frames/1000),(unsigned long long)(render_max/1000));
    fx_sfx_close();if(psm_ready)psmExit();
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
    for(;;){
        while(!(command=__atomic_load_n(&fx_ui_command,__ATOMIC_ACQUIRE)))svcSleepThread(10000000);
        if(command<0){pthread_join(fx_ui_thread,NULL);fx_ui_created=0;return 0;}
        /* Main thread performs SD I/O while the UI keeps the loading spinner moving.
         * No guest can load either D3D9 copy until the complete transaction succeeds. */
        int renderer=fx_ui_view.renderer,selected=fx_ui_view.selected;
        int ready=fx_apply_renderer(RUNTIME_DIR,renderer)&&fx_apply_preset(RUNTIME_DIR,selected);
        if(__atomic_load_n(&fx_ui_command,__ATOMIC_ACQUIRE)<0){
            __atomic_store_n(&fx_boot_started,0,__ATOMIC_RELEASE);
            pthread_join(fx_ui_thread,NULL);fx_ui_created=0;return 0;
        }
        if(ready){log_line("[FEXTENDO-RENDERER] selected=%s verified=1",fx_renderer_ids[renderer]);break;}
        pthread_mutex_lock(&fx_ui_lock);
        fx_ui_view.screen=FX_FAILED;fx_ui_view.fatal=0;
        fx_ui_view.message="Could not prepare the renderer. Copy both renderer folders and check SD space.";
        __atomic_store_n(&fx_boot_started,0,__ATOMIC_RELEASE);
        __atomic_store_n(&fx_ui_command,0,__ATOMIC_RELEASE);
        pthread_mutex_unlock(&fx_ui_lock);
    }
#ifdef WINE_NX_LSFG
    wine_nx_lsfg_configure(fx_ui_view.frame_generation,1,1);
#endif
    atexit(fx_exit_check);
    log_line("[FEXTENDO] launch requested; canonical settings=C:\\KONAMI\\Pro Evolution Soccer 2013\\settings.dat; VSync=on");
    return 1;
}
#endif
