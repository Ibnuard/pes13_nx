/* LGPL-2.1-or-later. Optional independent VI layer, never the game window.
 * The small 10Hz stopwatch keeps moving even if the game stops presenting.
 * OFF creates no worker/layer. Failures disable only the overlay. */
static uint64_t fx_timestamp_origin;
static int fx_timestamp_enabled,fx_timestamp_created,fx_timestamp_stop_requested;
static pthread_t fx_timestamp_thread;
extern u64 __nx_vi_layer_id;

static void fx_timestamp_arm(int enabled,uint64_t tick) {
    __atomic_store_n(&fx_timestamp_origin,tick,__ATOMIC_RELEASE);
    __atomic_store_n(&fx_timestamp_enabled,enabled,__ATOMIC_RELEASE);
    log_line("[FEXTENDO-TIME] origin_tick=%llu enabled=%d units=19200000_ticks_per_second; T+ starts at Play",
             (unsigned long long)tick,enabled);
}
static uint64_t fx_timestamp_elapsed(uint64_t tick) {
    uint64_t origin=__atomic_load_n(&fx_timestamp_origin,__ATOMIC_ACQUIRE);
    return origin&&tick>=origin?armTicksToNs(tick-origin)/1000000:0;
}
static void fx_timestamp_report(void) {
    if(!__atomic_load_n(&fx_timestamp_enabled,__ATOMIC_ACQUIRE))return;
    uint64_t tick=armGetSystemTick();
    log_line("[FEXTENDO-TIME] elapsed_ms=%llu tick=%llu",(unsigned long long)fx_timestamp_elapsed(tick),(unsigned long long)tick);
}
static void *fx_timestamp_main(void *unused) {
    ViDisplay display={0};ViLayer layer={0};NWindow window={0};Framebuffer fb={0};
    int have_window=0,have_fb=0;Result rc=0;s32 z=0;
    (void)unused;
    /* A externally supplied layer id could alias the game; never open it. */
    if(__nx_vi_layer_id){log_line("[FEXTENDO-TIME] overlay unavailable: external default layer override");return NULL;}
    if(R_FAILED(rc=viOpenDefaultDisplay(&display)))goto done;
    if(R_FAILED(rc=viCreateLayer(&display,&layer)))goto done;
    if(R_FAILED(rc=viSetLayerSize(&layer,FX_TIME_W,FX_TIME_H)))goto done;
    if(R_FAILED(rc=viSetLayerPosition(&layer,1032.0f,78.0f)))goto done;
    if(R_FAILED(rc=viGetZOrderCountMax(&display,&z)))goto done;
    if(R_FAILED(rc=viSetLayerZ(&layer,z)))goto done;
    if(R_FAILED(rc=viSetLayerScalingMode(&layer,ViScalingMode_None)))goto done;
    if(R_FAILED(rc=nwindowCreateFromLayer(&window,&layer)))goto done;
    have_window=1;
    if(R_FAILED(rc=framebufferCreate(&fb,&window,FX_TIME_W,FX_TIME_H,PIXEL_FORMAT_RGBA_8888,2)))goto done;
    have_fb=1;
    if(R_FAILED(rc=framebufferMakeLinear(&fb)))goto done;
    log_line("[FEXTENDO-TIME] overlay ready layer=%llu size=224x32 update_hz=10; separate from game Present",
             (unsigned long long)layer.layer_id);
    while(!__atomic_load_n(&fx_timestamp_stop_requested,__ATOMIC_ACQUIRE)){
        if(appletGetFocusState()!=AppletFocusState_InFocus){svcSleepThread(100000000);continue;}
        u32 stride;uint64_t tick=armGetSystemTick();
        uint32_t *pixels=framebufferBegin(&fb,&stride);
        if(!pixels)break;
        fx_timestamp_pixels(pixels,stride/4,fx_timestamp_elapsed(tick));
        framebufferEnd(&fb);
        uint64_t elapsed=armTicksToNs(armGetSystemTick()-tick);
        if(elapsed<100000000)svcSleepThread(100000000-elapsed);
    }
done:
    if(have_fb)framebufferClose(&fb);
    if(have_window)nwindowClose(&window);
    if(layer.initialized)viCloseLayer(&layer);
    if(display.initialized)viCloseDisplay(&display);
    if(R_FAILED(rc))log_line("[FEXTENDO-TIME] overlay unavailable rc=0x%x; game continues",(unsigned)rc);
    return NULL;
}
static void fx_timestamp_shutdown(void) {
    if(!fx_timestamp_created)return;
    __atomic_store_n(&fx_timestamp_stop_requested,1,__ATOMIC_RELEASE);
    pthread_join(fx_timestamp_thread,NULL);fx_timestamp_created=0;
}
static void fx_timestamp_start(void) {
    pthread_attr_t attr;int rc;
    if(!__atomic_load_n(&fx_timestamp_enabled,__ATOMIC_ACQUIRE)||fx_timestamp_created)return;
    if(pthread_attr_init(&attr))return;
    rc=pthread_attr_setstacksize(&attr,64*1024);
    if(!rc)rc=pthread_create(&fx_timestamp_thread,&attr,fx_timestamp_main,NULL);
    pthread_attr_destroy(&attr);
    if(rc){log_line("[FEXTENDO-TIME] overlay worker unavailable rc=%d",rc);return;}
    fx_timestamp_created=1;atexit(fx_timestamp_shutdown);
}
