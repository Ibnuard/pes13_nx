/* LGPL-2.1-or-later. A single UI thread owns and releases its framebuffer.
 * The thread and artwork are gone before Wine acquires the 3D surface. */
#ifndef FEXTENDO_LAUNCHER_H
#define FEXTENDO_LAUNCHER_H
#include <pthread.h>
#ifndef FX_SPLASH_MS
#define FX_SPLASH_MS 2400
#endif
#define FX_UI_FRAME_NS 16666667ull
#ifdef FX_SCREEN_DEBUG
#include "fextendo_debug_console.h"
#include "fextendo_debug_file.h"
#endif

static pthread_t fx_ui_thread;
static pthread_mutex_t fx_ui_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t fx_handoff_lock=PTHREAD_MUTEX_INITIALIZER;
static int fx_ui_created,fx_ui_owned,fx_ui_stop,fx_ui_command,fx_boot_started,fx_first_present;
static struct fx_view fx_ui_view={.screen=FX_HOME,.sound=1,.battery=-1};
static char fx_ui_message[192];
#include "fextendo_runtime_api.h"
static int fx_repair_cancelled;
static int fx_repair_cancel(void){return __atomic_load_n(&fx_repair_cancelled,__ATOMIC_ACQUIRE)||__atomic_load_n(&fx_ui_command,__ATOMIC_ACQUIRE)<0;}
static void fx_repair_progress(int phase,uint64_t current,uint64_t total,const char *name){
    static const char *const labels[]={"Checking runtime","Downloading runtime","Verifying package","Installing runtime","Recovering previous runtime"};
    pthread_mutex_lock(&fx_ui_lock);
    fx_ui_view.repair_percent=total?(int)(current*100/total):0;
    fx_ui_view.repair_finishing=phase==FXR_INSTALL||phase==FXR_RECOVER;
    snprintf(fx_ui_message,sizeof(fx_ui_message),"%s: %s",labels[phase],name);
    fx_ui_view.message=fx_ui_message;pthread_mutex_unlock(&fx_ui_lock);
}
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
#ifdef FX_SCREEN_DEBUG
        fx_launch_debug_handoff();
#endif
        log_line("[FEXTENDO] launcher stopped and framebuffer released before 3D handoff");
        if(!fx_pads_begin_game()){
            pthread_mutex_lock(&fx_ui_lock);fx_ui_view.screen=FX_FAILED;fx_ui_view.fatal=1;
            pthread_mutex_unlock(&fx_ui_lock);
            fx_native_error("Controller recovery could not start. Close and relaunch.");failed=1;
        }else fx_timestamp_start();
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
    struct fx_art art;Framebuffer fb;Result rc;uint64_t previous_buttons=0;int input_drain=0;int pending=0,last_dir=0,psm_ready=0,splash_done=0;u64 repeat=0,started=0,last_frame=0,battery_due=0,ui_origin=0;
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
    fx_pads_init();fx_ui_view.players=fx_pads_players();
    __atomic_store_n(&fx_ui_owned,1,__ATOMIC_RELEASE);
    if(!fx_renderer_recover(RUNTIME_DIR)||!fx_recover(RUNTIME_DIR)){
        fx_ui_view.screen=FX_FAILED;fx_ui_view.fatal=1;
        fx_ui_view.message="Settings recovery failed. Check SD card space.";
    }
    fx_ui_view.selected=fx_selected(RUNTIME_DIR);
    fx_ui_view.renderer=fx_renderer_selected(RUNTIME_DIR);
    fx_keyboard_options=fx_keyboard_options_load(RUNTIME_DIR);
    fx_ui_view.timestamp=fx_debug_timestamp(RUNTIME_DIR);
#ifdef FX_SCREEN_DEBUG
    fx_ui_view.debug_launch=fx_debug_launch(RUNTIME_DIR);
#endif
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
        fx_pads_snapshot(fx_ui_view.pads);fx_ui_view.players=fx_pads_players();
        held=fx_pad_navigation(&fx_ui_view.pads[0])|fx_pad_navigation(&fx_ui_view.pads[1]);
        down=held&~previous_buttons;previous_buttons=held;
        if(input_drain){
            if(fx_pad_neutral(&fx_ui_view.pads[0])&&fx_pad_neutral(&fx_ui_view.pads[1]))input_drain=0;
            down=held=0;
        }
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
            int tiles=fx_ui_view.debug_launch?5:4;
            if(dir)fx_ui_view.tile=(fx_ui_view.tile+dir+tiles)%tiles;
            if(down&HidNpadButton_B)fx_ui_view.tile=0;
            if(confirm&&fx_ui_view.tile==3){fx_ui_view.screen=FX_CREDITS;fx_ui_view.credit_page=0;}
            else if(confirm&&fx_ui_view.tile==2){fx_ui_view.screen=FX_GAMEPAD;fx_ui_view.row=0;fx_ui_view.message=NULL;fx_ui_view.pad_test=0;}
            else if(confirm&&fx_ui_view.tile==1){fx_ui_view.screen=FX_SETTINGS;fx_settings_enter(&fx_ui_view,FX_SETTINGS_ROOT,0);}
            else if(confirm&&!fx_pads_ready()){
                fx_ui_view.screen=FX_GAMEPAD;fx_ui_view.row=0;fx_ui_view.pad_test=0;
                fx_ui_view.message="Connect a Player 1 controller before Play.";
            }
            else if(confirm&&fx_ui_view.repair_blocked){
                fx_ui_view.screen=FX_SETTINGS;fx_settings_enter(&fx_ui_view,FX_SETTINGS_MAINTENANCE,1);
            }
            else if(confirm){
                FILE *game=fopen(DEFAULT_TARGET,"rb");
                if(!game){fx_ui_view.screen=FX_FAILED;fx_ui_view.fatal=0;fx_ui_view.message="PES13 was not found. Check the game folder.";}
                else{
                    fclose(game);
                    if(!fx_pads_capture_session()){
                        fx_ui_view.screen=FX_GAMEPAD;fx_ui_view.row=0;fx_ui_view.pad_test=0;
                        fx_ui_view.message="Controller disconnected. Select Change Controller.";
                        pthread_mutex_unlock(&fx_ui_lock);continue;
                    }
                    fx_timestamp_arm(fx_ui_view.timestamp,frame_start);
#ifdef FX_SCREEN_DEBUG
                    fx_debug_file_begin(fx_ui_view.tile==4);
                    fx_launch_debug_log("[STARTUP] FEXTendo " FX_APP_VERSION " / startup console / debug files enabled");
#endif
                    fx_ui_view.screen=FX_LOADING;fx_ui_view.message="Preparing your game...";pending=1;started=frame_start;
                }
            }
        }else if(fx_ui_view.screen==FX_SETTINGS){
            int rows=fx_settings_rows(fx_ui_view.settings_page);
            if(dir){fx_ui_view.row=(fx_ui_view.row+dir+rows)%rows;fx_ui_view.saved=0;}
            if(down&HidNpadButton_B)fx_settings_back(&fx_ui_view);
            else if(confirm){
                int music=fx_ui_view.music;
                if(fx_ui_view.settings_page==FX_SETTINGS_MAINTENANCE){
                    fx_ui_view.screen=FX_REPAIR;fx_ui_view.repair_busy=1;
                    fx_ui_view.repair_finishing=0;fx_ui_view.repair_percent=0;
                    fx_ui_view.message="Preparing runtime check...";
                    __atomic_store_n(&fx_repair_cancelled,0,__ATOMIC_RELEASE);
                    __atomic_store_n(&fx_ui_command,fx_ui_view.row?3:2,__ATOMIC_RELEASE);
                }else
                if(!fx_settings_choose(&fx_ui_view,RUNTIME_DIR)){
                    fx_ui_view.screen=FX_FAILED;fx_ui_view.fatal=0;
                    fx_ui_view.message="Could not save settings. Check the SD card.";
                }
                if(music!=fx_ui_view.music)fx_music_set(fx_ui_view.music);
            }
        }else if(fx_ui_view.screen==FX_REPAIR){
            if(down&HidNpadButton_B){
                if(fx_ui_view.repair_busy){
                    if(!fx_ui_view.repair_finishing)__atomic_store_n(&fx_repair_cancelled,1,__ATOMIC_RELEASE);
                }else{fx_ui_view.screen=FX_SETTINGS;fx_settings_enter(&fx_ui_view,FX_SETTINGS_MAINTENANCE,0);}
            }
        }else if(fx_ui_view.screen==FX_GAMEPAD){
            if(fx_ui_view.pad_test){
                if(down&(HidNpadButton_Plus|HidNpadButton_Minus)){fx_ui_view.pad_test=0;input_drain=1;}
            }else if(down&(HidNpadButton_B|HidNpadButton_Plus))fx_ui_view.screen=FX_HOME;
            else if(confirm){
                if(fx_ui_view.row==0){
                    pthread_mutex_unlock(&fx_ui_lock);
                    int connected=fx_pads_connect();
                    pthread_mutex_lock(&fx_ui_lock);
                    fx_ui_view.message=connected?"Controller setup closed. Check both slots above.":"Controller setup cancelled or unavailable. Please retry.";
                    input_drain=1;last_dir=0;previous_buttons=0;
                }else{fx_ui_view.pad_test=1;fx_ui_view.message=NULL;input_drain=1;}
            }else if(dir)fx_ui_view.row=(fx_ui_view.row+dir+2)%2;
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
        if(fx_ui_view.screen==FX_GAMEPAD&&fx_ui_view.pad_test){}
        else if(confirm)fx_sfx_play(fx_ui_view.screen==FX_FAILED?FX_ERROR:FX_CONFIRM,fx_ui_view.sound);
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
        if(pixels){struct fx_canvas c={pixels,(int)stride/4,&art};
#ifdef FX_SCREEN_DEBUG
            if(fx_ui_view.screen==FX_LOADING&&fx_launch_debug_startup()){
                struct fx_debug_snapshot snap={0};fx_launch_debug_snapshot(&snap);fx_debug_draw(&c,&snap);
            }else
#endif
            fx_render(&c,&fx_ui_view);
            framebufferEnd(&fb);
        }
        u64 render_ns=armTicksToNs(armGetSystemTick()-render_start);
        render_sum+=render_ns;render_frames++;if(render_ns>render_max)render_max=render_ns;
        pthread_mutex_unlock(&fx_ui_lock);
        u64 elapsed=armTicksToNs(armGetSystemTick()-frame_start);
        u64 interval=FX_UI_FRAME_NS;
#ifdef FX_SCREEN_DEBUG
        if(fx_launch_debug_startup())interval=200000000ull;
#endif
        if(elapsed<interval)svcSleepThread(interval-elapsed);
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
    struct fxr_job recovery={.root=RUNTIME_DIR};
    if(!fx_runtime_recover(&recovery)){fx_native_error(recovery.error[0]?recovery.error:"Runtime recovery failed. Keep the repair folder.");return 0;}
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
        if(command==2||command==3){
            struct fxr_job job={.root=RUNTIME_DIR,.progress=fx_repair_progress,.cancelled=fx_repair_cancel};
            int ok=fx_runtime_recover(&job)&&fx_runtime_check(&job);
            if(ok&&command==3)ok=fx_runtime_repair(&job);
            struct fxr_job restore={.root=RUNTIME_DIR};
            int recovered=fx_runtime_recover(&restore);
            pthread_mutex_lock(&fx_ui_lock);
            fx_ui_view.repair_blocked=!recovered;fx_ui_view.repair_busy=fx_ui_view.repair_finishing=0;
            if(!recovered)snprintf(fx_ui_message,sizeof(fx_ui_message),"%s",restore.error[0]?restore.error:"Recovery failed. Keep the repair folder and check the SD card.");
            else if(!ok)snprintf(fx_ui_message,sizeof(fx_ui_message),"%s",job.error[0]?job.error:"Runtime operation failed. Check SD card space.");
            else if(!job.changed)snprintf(fx_ui_message,sizeof(fx_ui_message),"All %u runtime files verified. No repair needed.",fx_runtime_file_count());
            else if(command==2)snprintf(fx_ui_message,sizeof(fx_ui_message),"%u runtime files are missing or damaged. Choose Repair runtime to restore them.",job.changed);
            else snprintf(fx_ui_message,sizeof(fx_ui_message),"Repaired %u runtime files. Ready to launch.",job.changed);
            fx_ui_view.message=fx_ui_message;
            if(__atomic_load_n(&fx_ui_command,__ATOMIC_ACQUIRE)>=0)__atomic_store_n(&fx_ui_command,0,__ATOMIC_RELEASE);
            pthread_mutex_unlock(&fx_ui_lock);continue;
        }
        /* Main thread performs SD I/O while the UI keeps the loading spinner moving.
         * No guest can load either D3D9 copy until the complete transaction succeeds. */
        int renderer=fx_ui_view.renderer,selected=fx_ui_view.selected;
#ifdef FX_SCREEN_DEBUG
        fx_debug_file_prepare(RUNTIME_DIR);
        if(wine_nx_launch_debug_active()){
            if(!__atomic_load_n(&fx_crash_ready,__ATOMIC_ACQUIRE))fx_crash_bootstrap();
            fx_crash_settings(selected,renderer);
            fx_launch_debug_log("[CRASH] capture_ready=%u",__atomic_load_n(&fx_crash_ready,__ATOMIC_ACQUIRE));
            fx_launch_debug_log("[MEMORY] mode=%s base=%llx span=%llx alias=%llx",
                fx_memory_mode_name(fx_memory_mode(&fx_startup_memory)),
                (unsigned long long)fx_startup_memory.base,(unsigned long long)fx_startup_memory.size,
                (unsigned long long)fx_startup_memory.alias);
            u64 total=0,used=0;Result tr=svcGetInfo(&total,InfoType_TotalMemorySize,CUR_PROCESS_HANDLE,0);
            Result ur=svcGetInfo(&used,InfoType_UsedMemorySize,CUR_PROCESS_HANDLE,0);
            fx_launch_debug_log("[STARTUP] applet_type=%d total_mb=%llu used_mb=%llu query_rc=%x/%x",
                (int)appletGetAppletType(),(unsigned long long)(total>>20),(unsigned long long)(used>>20),tr,ur);
            fx_launch_debug_log("[STARTUP] preset=%s renderer=%s",fx_preset_names[selected],fx_renderer_names[renderer]);
        }
#endif
        log_line("[STARTUP] verifying renderer files...");
        int ready=fx_apply_renderer(RUNTIME_DIR,renderer);
        log_line("[STARTUP] renderer ready=%d; verifying game settings...",ready);
        if(ready)ready=fx_apply_preset(RUNTIME_DIR,selected);
        log_line("[STARTUP] game settings ready=%d",ready);
        if(ready&&wine_nx_launch_debug_active())for(unsigned i=0;i<3;i++){
            unsigned flags=0;int valid=fx_settings_flags(RUNTIME_DIR,i,&flags);
            log_line("[SETTINGS-VERIFY] path=%s crc_valid=%d flags=%04x vsync=%u frame_skip=%u xinput=%u",
                     fx_targets[i],valid,flags,!!(flags&FX_SETTINGS_VSYNC),
                     !!(flags&FX_SETTINGS_FRAME_SKIP),(flags&FX_SETTINGS_XINPUT)==FX_SETTINGS_XINPUT);
        }
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
    atexit(fx_exit_check);
    log_line("[FEXTENDO] launch requested; canonical settings=C:\\KONAMI\\Pro Evolution Soccer 2013\\settings.dat; VSync=on");
    return 1;
}
#endif
