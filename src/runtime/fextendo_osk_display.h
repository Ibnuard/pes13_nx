/* LGPL-2.1-or-later. Only the controller monitor owns this VI surface. */
#include "fextendo_osk_ui.h"
static struct fx_pause_display fx_osk_display;
static unsigned fx_osk_drawn_generation;
static int fx_osk_display_mode=-1;
static void fx_osk_display_close(void) {
    fx_pause_close(&fx_osk_display);fx_osk_drawn_generation=0;fx_osk_display_mode=-1;
}
static int fx_osk_display_show(const struct fx_osk_core *state,unsigned player,int single) {
    struct fx_pause_display *p=&fx_osk_display;
    int mode=appletGetOperationMode();s32 w=1280,h=720,z=0;
    if(p->have_fb&&fx_osk_drawn_generation==state->generation&&fx_osk_display_mode==mode)return 1;
    if(!p->have_fb){
        if(!fx_font_load(&p->art,RUNTIME_DIR))goto fail;
        if(R_FAILED(fx_overlay_display_open(&p->display,&p->borrowed)))goto fail;
        if(R_FAILED(fx_overlay_layer_create(&p->display,&p->layer)))goto fail;
        if(R_FAILED(fx_overlay_stack(&p->layer,ViLayerStack_Default))||R_FAILED(fx_overlay_stack(&p->layer,ViLayerStack_Lcd)))goto fail;
        if(R_FAILED(viGetZOrderCountMax(&p->display,&z))||R_FAILED(viSetLayerZ(&p->layer,z)))goto fail;
        if(R_FAILED(viSetLayerScalingMode(&p->layer,ViScalingMode_FitToLayer)))goto fail;
        if(R_FAILED(nwindowCreateFromLayer(&p->window,&p->layer)))goto fail;
        p->have_window=1;
        if(R_FAILED(framebufferCreate(&p->fb,&p->window,FX_W,FX_OSK_HEIGHT,PIXEL_FORMAT_RGBA_8888,2)))goto fail;
        p->have_fb=1;
        if(R_FAILED(framebufferMakeLinear(&p->fb)))goto fail;
    }
    viGetDisplayLogicalResolution(&p->display,&w,&h);if(w<=0||h<=0){w=1280;h=720;}
    if(R_FAILED(viSetLayerSize(&p->layer,w,h/2))||R_FAILED(viSetLayerPosition(&p->layer,0,state->top?0:h/2)))goto fail;
    u32 stride;uint32_t *pixels=framebufferBegin(&p->fb,&stride);
    if(!pixels)goto fail;
    struct fx_canvas canvas={.pixels=pixels,.stride=(int)stride/4,.art=&p->art,.clip_bottom=FX_OSK_HEIGHT};
    fx_osk_draw(&canvas,state,player,single);framebufferEnd(&p->fb);
    fx_osk_drawn_generation=state->generation;fx_osk_display_mode=mode;return 1;
fail:fx_osk_display_close();return 0;
}
static int fx_osk_touch(int *x,int *y) {
    HidTouchScreenState touch;
    if(!hidGetTouchScreenStates(&touch,1)||!touch.count)return 0;
    *x=touch.touches[0].x;*y=touch.touches[0].y;return 1;
}
