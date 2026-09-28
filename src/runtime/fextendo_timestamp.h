/* LGPL-2.1-or-later. Optional independent VI layer, never the game window.
 * The small 10Hz stopwatch keeps moving even if the game stops presenting.
 * OFF creates no worker/layer. Failures disable only the overlay. */
static uint64_t fx_timestamp_origin;
static int fx_timestamp_enabled,fx_timestamp_created,fx_timestamp_stop_requested;
static pthread_t fx_timestamp_thread;


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
static void *fx_timestamp_main(void *unused) {
    ViDisplay display={0};ViLayer layer={0};NWindow window={0};Framebuffer fb={0};
    int have_window=0,have_fb=0;Result rc=0;s32 z=0,width=1920,height=1080;
    const char *stage="display";
    (void)unused;
    if(R_FAILED(rc=viOpenDefaultDisplay(&display)))goto done;
    stage="independent managed layer";
    if(R_FAILED(rc=fx_overlay_layer_create(&display,&layer)))goto done;
    stage="display stacks";
    if(R_FAILED(rc=fx_overlay_stack(&layer,ViLayerStack_Default)))goto done;
    if(R_FAILED(rc=fx_overlay_stack(&layer,ViLayerStack_Lcd)))goto done;
    /* Capture stacks are independent of on-screen display availability. */
    for(unsigned stack=ViLayerStack_Screenshot;stack<=ViLayerStack_Recording;stack++){
        Result capture=fx_overlay_stack(&layer,stack);
        if(R_FAILED(capture))log_line("[FEXTENDO-TIME] capture stack=%u rc=0x%x",stack,(unsigned)capture);
    }
    viGetDisplayLogicalResolution(&display,&width,&height);
    if(width<=0||height<=0){width=1920;height=1080;}
    stage="geometry";
    if(R_FAILED(rc=viSetLayerSize(&layer,FX_TIME_W*width/1280,FX_TIME_H*height/720)))goto done;
    if(R_FAILED(rc=viSetLayerPosition(&layer,(1280-FX_TIME_W-24)*width/1280.f,92*height/720.f)))goto done;
    stage="z-order";
    if(R_FAILED(rc=viGetZOrderCountMax(&display,&z)))goto done;
    if(R_FAILED(rc=viSetLayerZ(&layer,z)))goto done;
    if(R_FAILED(rc=viSetLayerScalingMode(&layer,ViScalingMode_FitToLayer)))goto done;
    stage="window/framebuffer";
    if(R_FAILED(rc=nwindowCreateFromLayer(&window,&layer)))goto done;
    have_window=1;
    if(R_FAILED(rc=framebufferCreate(&fb,&window,FX_TIME_W,FX_TIME_H,PIXEL_FORMAT_RGBA_8888,2)))goto done;
    have_fb=1;
    if(R_FAILED(rc=framebufferMakeLinear(&fb)))goto done;
    char font_path[768];snprintf(font_path,sizeof(font_path),"%s/launcher/timestamp-font.bin",RUNTIME_DIR);
    fx_timestamp_font_ready=fx_read(font_path,fx_timestamp_font,sizeof(fx_timestamp_font))==sizeof(fx_timestamp_font);
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
    if(layer.layer_id)fx_overlay_layer_close(&layer);
    if(display.initialized)viCloseDisplay(&display);
    if(R_FAILED(rc))log_line("[FEXTENDO-TIME] overlay unavailable stage=%s rc=0x%x; game continues",stage,(unsigned)rc);
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
    __atomic_store_n(&fx_timestamp_stop_requested,0,__ATOMIC_RELEASE);
    if(!rc)rc=pthread_create(&fx_timestamp_thread,&attr,fx_timestamp_main,NULL);
    pthread_attr_destroy(&attr);
    if(rc){log_line("[FEXTENDO-TIME] overlay worker unavailable rc=%d",rc);return;}
    fx_timestamp_created=1;atexit(fx_timestamp_shutdown);
}
