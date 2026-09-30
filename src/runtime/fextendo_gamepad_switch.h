/* LGPL-2.1-or-later. Included once by runtime.c, after UI/VI helpers.
 * Native input has one owner/configuration. No Wine or FEX worker is suspended
 * while holding arbitrary locks: game entry points wait at input/frame boundaries. */
#include "fextendo_gamepad.h"
static pthread_once_t fx_pad_once=PTHREAD_ONCE_INIT;
static pthread_mutex_t fx_pad_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t fx_pad_applet_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t fx_pad_cond=PTHREAD_COND_INITIALIZER;
static PadState fx_native_pads[2];
static struct fx_pad_sample fx_samples[2];
static struct fx_reconnect fx_recovery;
static unsigned fx_players=1;
static int fx_game_active,fx_game_paused,fx_pad_stop,fx_pad_thread_created,fx_pad_session_captured;
static pthread_t fx_pad_thread;

static void fx_pads_once(void) {
    padConfigureInput(2,HidNpadStyleSet_NpadStandard|HidNpadStyleTag_NpadJoyLeft|HidNpadStyleTag_NpadJoyRight);
    hidSetNpadJoyHoldType(HidNpadJoyHoldType_Horizontal);
    padInitializeDefault(&fx_native_pads[0]);
    padInitialize(&fx_native_pads[1],HidNpadIdType_No2);
}
void fx_pads_init(void) {pthread_once(&fx_pad_once,fx_pads_once);}
unsigned fx_pads_players(void) {fx_pads_init();return __atomic_load_n(&fx_players,__ATOMIC_ACQUIRE);}
static unsigned fx_pads_mask(void) {
    return (fx_samples[0].connected?1u:0u)|(fx_samples[1].connected?2u:0u);
}
static void fx_pads_poll_locked(void) {
    for(unsigned i=0;i<2;i++){
        PadState *p=&fx_native_pads[i];padUpdate(p);
        u32 style=padGetStyleSet(p),attr=padGetAttributes(p);int kind=FX_PAD_FULL,connected=padIsConnected(p);
        if(style&HidNpadStyleTag_NpadHandheld)kind=FX_PAD_HANDHELD;
        else if(style&HidNpadStyleTag_NpadJoyDual){
            kind=FX_PAD_DUAL;
            if(!(attr&HidNpadAttribute_IsLeftConnected)||!(attr&HidNpadAttribute_IsRightConnected))connected=0;
        }else if(style&HidNpadStyleTag_NpadJoyLeft)kind=FX_PAD_LEFT;
        else if(style&HidNpadStyleTag_NpadJoyRight)kind=FX_PAD_RIGHT;
        HidAnalogStickState l=padGetStickPos(p,0),r=padGetStickPos(p,1);
        fx_pad_update(&fx_samples[i],fx_pad_normalize(kind,connected,padGetButtons(p),l.x,l.y,r.x,r.y));
    }
    if(!fx_pad_session_captured)__atomic_store_n(&fx_players,fx_samples[1].connected?2:1,__ATOMIC_RELEASE);
    /* P2 may join later, but a loss must never silently shrink an active session. */
    if(fx_game_active&&fx_samples[1].connected){
        fx_recovery.required|=2;__atomic_store_n(&fx_players,2,__ATOMIC_RELEASE);
    }
    if(fx_game_active&&fx_reconnect_poll(&fx_recovery,fx_pads_mask(),0,0))
        __atomic_store_n(&fx_game_paused,1,__ATOMIC_RELEASE);
}
void fx_pads_snapshot(struct fx_pad_sample out[2]) {
    fx_pads_init();pthread_mutex_lock(&fx_pad_lock);fx_pads_poll_locked();
    memcpy(out,fx_samples,sizeof(fx_samples));pthread_mutex_unlock(&fx_pad_lock);
}
int fx_pads_ready(void) {
    struct fx_pad_sample p[2];fx_pads_snapshot(p);
    return p[0].connected;
}
/* Keep the one-shot Play boundary visible to the linked startup regression. */
int __attribute__((noinline)) fx_pads_capture_session(void) {
    fx_pads_init();pthread_mutex_lock(&fx_pad_lock);fx_pads_poll_locked();
    int ready=fx_samples[0].connected;
    if(ready){fx_pad_session_captured=1;fx_recovery.required=(1u<<fx_players)-1;}
    pthread_mutex_unlock(&fx_pad_lock);return ready;
}
int fx_pads_connect(void) {
    HidLaControllerSupportArg arg;HidLaControllerSupportResultInfo result={0};Result rc;
    fx_pads_init();pthread_mutex_lock(&fx_pad_applet_lock);
    hidLaCreateControllerSupportArg(&arg);
    /* A pre-game Change Controller always accepts either one or two players. */
    pthread_mutex_lock(&fx_pad_lock);
    arg.hdr.player_count_min=fx_game_active?fx_players:1;
    pthread_mutex_unlock(&fx_pad_lock);
    arg.hdr.player_count_max=2;
    arg.hdr.enable_take_over_connection=1;arg.hdr.enable_left_justify=0;
    arg.hdr.enable_permit_joy_dual=1;arg.hdr.enable_single_mode=0;
    arg.enable_explain_text=1;
    hidLaSetExplainText(&arg,"Player 1",HidNpadIdType_No1);
    hidLaSetExplainText(&arg,"Player 2",HidNpadIdType_No2);
    /* Explicit Change Grip/Order must display even when both slots are ready. */
    rc=hidLaShowControllerSupportForSystem(&result,&arg,true);
    pthread_mutex_unlock(&fx_pad_applet_lock);return R_SUCCEEDED(rc);
}
int fx_pads_paused(void) {return __atomic_load_n(&fx_game_paused,__ATOMIC_ACQUIRE);}
void wine_nx_gamepad_wait(void) {
    if(!fx_pads_paused())return;
    pthread_mutex_lock(&fx_pad_lock);
    while(fx_pads_paused())pthread_cond_wait(&fx_pad_cond,&fx_pad_lock);
    pthread_mutex_unlock(&fx_pad_lock);
}
int fx_pads_game_state(unsigned index,struct fx_pad_sample *out) {
    memset(out,0,sizeof(*out));if(index>=2)return 0;fx_pads_init();
    for(;;){
        wine_nx_gamepad_wait();
        pthread_mutex_lock(&fx_pad_lock);fx_pads_poll_locked();
        if(fx_pads_paused()){pthread_mutex_unlock(&fx_pad_lock);continue;}
        *out=fx_samples[index];pthread_mutex_unlock(&fx_pad_lock);return out->connected;
    }
}
struct fx_pause_display {
    ViDisplay display;ViLayer layer;NWindow window;Framebuffer fb;struct fx_art art;
    int borrowed,have_window,have_fb;
};
static void fx_pause_close(struct fx_pause_display *p) {
    if(p->have_fb)framebufferClose(&p->fb);
    if(p->have_window)nwindowClose(&p->window);
    if(p->layer.layer_id)fx_overlay_layer_close(&p->layer);
    if(p->display.initialized&&!p->borrowed)viCloseDisplay(&p->display);
    free(p->art.font);memset(p,0,sizeof(*p));
}
static int fx_pause_open(struct fx_pause_display *p) {
    s32 w=1280,h=720,z=0;
    if(!fx_font_load(&p->art,RUNTIME_DIR))goto fail;
    if(R_FAILED(fx_overlay_display_open(&p->display,&p->borrowed)))goto fail;
    if(R_FAILED(fx_overlay_layer_create(&p->display,&p->layer)))goto fail;
    if(R_FAILED(fx_overlay_stack(&p->layer,ViLayerStack_Default))||R_FAILED(fx_overlay_stack(&p->layer,ViLayerStack_Lcd)))goto fail;
    viGetDisplayLogicalResolution(&p->display,&w,&h);if(w<=0||h<=0){w=1280;h=720;}
    if(R_FAILED(viSetLayerSize(&p->layer,w,h))||R_FAILED(viSetLayerPosition(&p->layer,0,0)))goto fail;
    if(R_FAILED(viGetZOrderCountMax(&p->display,&z))||R_FAILED(viSetLayerZ(&p->layer,z)))goto fail;
    if(R_FAILED(viSetLayerScalingMode(&p->layer,ViScalingMode_FitToLayer)))goto fail;
    if(R_FAILED(nwindowCreateFromLayer(&p->window,&p->layer)))goto fail;p->have_window=1;
    if(R_FAILED(framebufferCreate(&p->fb,&p->window,FX_W,FX_H,PIXEL_FORMAT_RGBA_8888,2)))goto fail;p->have_fb=1;
    if(R_FAILED(framebufferMakeLinear(&p->fb)))goto fail;
    return 1;
fail:fx_pause_close(p);return 0;
}
static void fx_pause_display_failed(void) {
    ErrorApplicationConfig error;
    if(R_SUCCEEDED(errorApplicationCreate(&error,"Layar pause FEXTendo tidak tersedia.",
        "Game dihentikan agar tidak berjalan tanpa controller. Tutup dan jalankan kembali FEXTendo.")))errorApplicationShow(&error);
    exit(1);
}
static void *fx_pads_monitor(void *unused) {
    struct fx_pause_display display={0};uint64_t previous=0;int applet_ok=1;
    (void)unused;
    while(!__atomic_load_n(&fx_pad_stop,__ATOMIC_ACQUIRE)){
        /* This worker takes over libnx applet events after launcher handoff. */
        if(!appletMainLoop())exit(0);
        if(appletGetFocusState()!=AppletFocusState_InFocus){svcSleepThread(20000000);continue;}
        struct fx_pad_sample p[2];fx_pads_snapshot(p);
        if(!fx_pads_paused()){svcSleepThread(20000000);continue;}
        pthread_mutex_lock(&fx_pad_lock);int open=fx_recovery.phase==FX_RECONNECT_APPLET;
        pthread_mutex_unlock(&fx_pad_lock);
        if(open){
            /* Never hold the input mutex across an applet or VI operation. */
            fx_pause_close(&display);applet_ok=fx_pads_connect();previous=0;
            pthread_mutex_lock(&fx_pad_lock);fx_recovery.phase=FX_RECONNECT_NEUTRAL;
            pthread_mutex_unlock(&fx_pad_lock);continue;
        }
        if(!display.have_fb&&!fx_pause_open(&display))fx_pause_display_failed();
        uint64_t held=p[0].buttons|(fx_pads_players()==2?p[1].buttons:0),down=held&~previous;
        int neutral=fx_pad_neutral(&p[0])&&(fx_pads_players()==1||fx_pad_neutral(&p[1]));
        previous=held;
        pthread_mutex_lock(&fx_pad_lock);
        if(fx_recovery.phase==FX_RECONNECT_WAIT&&(down&FX_PAD_X))fx_recovery.phase=FX_RECONNECT_APPLET;
        else fx_reconnect_poll(&fx_recovery,fx_pads_mask(),neutral,!!(down&FX_PAD_A));
        enum fx_reconnect_phase phase=fx_recovery.phase;
        pthread_mutex_unlock(&fx_pad_lock);
        if(phase==FX_RECONNECT_RUNNING){
            fx_pause_close(&display);
            pthread_mutex_lock(&fx_pad_lock);
            /* A disconnect during VI teardown starts a new incident. */
            fx_pads_poll_locked();
            if(fx_recovery.phase==FX_RECONNECT_RUNNING){
                __atomic_store_n(&fx_game_paused,0,__ATOMIC_RELEASE);pthread_cond_broadcast(&fx_pad_cond);
            }
            pthread_mutex_unlock(&fx_pad_lock);continue;
        }
        if(phase==FX_RECONNECT_APPLET)continue;
        if(appletGetFocusState()!=AppletFocusState_InFocus){svcSleepThread(20000000);continue;}
        u32 stride;uint32_t *pixels=framebufferBegin(&display.fb,&stride);
        if(!pixels)fx_pause_display_failed();
        struct fx_canvas canvas={pixels,(int)stride/4,&display.art};
        fx_gamepad_pause(&canvas,p,fx_pads_players(),p[0].connected&&(fx_pads_players()==1||p[1].connected),
            phase!=FX_RECONNECT_WAIT,applet_ok);
        framebufferEnd(&display.fb);svcSleepThread(20000000);
    }
    fx_pause_close(&display);return NULL;
}
static void fx_pads_shutdown(void) {
    if(!fx_pad_thread_created)return;
    __atomic_store_n(&fx_pad_stop,1,__ATOMIC_RELEASE);
    /* exit() can originate in the monitor's fatal display path. */
    if(!pthread_equal(pthread_self(),fx_pad_thread))pthread_join(fx_pad_thread,NULL);
    fx_pad_thread_created=0;
}
int fx_pads_begin_game(void) {
    pthread_attr_t attr;int rc;
    fx_pads_init();if(fx_pad_thread_created)return 1;
    if(R_FAILED(appletSetFocusHandlingMode(AppletFocusHandlingMode_AlwaysSuspend)))return 0;
    if(pthread_attr_init(&attr))return 0;
    rc=pthread_attr_setstacksize(&attr,128*1024);
    pthread_mutex_lock(&fx_pad_lock);fx_recovery.required=(1u<<fx_players)-1;
    fx_game_active=1;fx_pads_poll_locked();pthread_mutex_unlock(&fx_pad_lock);
    if(!rc)rc=pthread_create(&fx_pad_thread,&attr,fx_pads_monitor,NULL);
    pthread_attr_destroy(&attr);
    if(rc){
        pthread_mutex_lock(&fx_pad_lock);fx_game_active=0;fx_recovery.phase=FX_RECONNECT_RUNNING;
        __atomic_store_n(&fx_game_paused,0,__ATOMIC_RELEASE);pthread_cond_broadcast(&fx_pad_cond);
        pthread_mutex_unlock(&fx_pad_lock);return 0;
    }
    fx_pad_thread_created=1;atexit(fx_pads_shutdown);return 1;
}
