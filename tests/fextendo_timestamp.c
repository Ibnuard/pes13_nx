/* Real overlay lifecycle and IPC payloads against a modeled VI service. */
#include <assert.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>
#include <stdarg.h>
#include <time.h>
#include "../src/runtime/fextendo_presets.h"
#include "../src/runtime/fextendo_renderers.h"
typedef uint64_t u64;typedef uint32_t u32;typedef int32_t s32;typedef int Result;
typedef struct {char data[64];} ViDisplayName;
typedef struct {int initialized;ViDisplayName display_name;u64 display_id;} ViDisplay;
typedef struct {int initialized;u64 layer_id;u32 igbp_binder_obj_id;} ViLayer;
typedef struct {pthread_t owner;} NWindow;
typedef struct {pthread_t owner;} Framebuffer;
typedef int Service;typedef int ViLayerFlags;
#define R_FAILED(x) ((x)!=0)
#define R_SUCCEEDED(x) ((x)==0)
#define MAKERESULT(a,b) (90+(b))
#define Module_Libnx 1
#define LibnxError_NotInitialized 1
#define LibnxError_BadInput 2
#define PIXEL_FORMAT_RGBA_8888 1
#define ViScalingMode_FitToLayer 2
#define ViLayerStack_Default 0
#define ViLayerStack_Lcd 1
#define ViLayerStack_Screenshot 2
#define ViLayerStack_Recording 3
#define AppletFocusState_InFocus 1
static const char *test_root;
#define RUNTIME_DIR test_root
static u64 appletGetAppletResourceUserId(void){return 0x12345678;}
static u64 __nx_vi_layer_id=7; /* supplied game layer must never be touched */
static unsigned step,fail_at,display_open,managed_open,layer_open,window_open,fb_open;
static unsigned frames,focus_skips,stack_mask;
static u64 ticks=1000000000;
static int focus=1,null_frame,manager=1,bad_parcel,borrow_display;
static uint32_t pixels[32][240];
static char messages[16384];
static int next(void){return ++step==fail_at?42:0;}
static Service *viGetSession_IManagerDisplayService(void){return &manager;}
static Service *viGetSession_IApplicationDisplayService(void){return &manager;}
static int serviceIsActive(Service *s){return *s;}
static u64 armGetSystemTick(void){return __atomic_load_n(&ticks,__ATOMIC_RELAXED);}
static u64 armTicksToNs(u64 v){return v;}
static void svcSleepThread(u64 n){
    __atomic_add_fetch(&ticks,n,__ATOMIC_RELAXED);
    if(!focus){focus_skips++;focus=1;}
    struct timespec t={0,1000000};nanosleep(&t,NULL);
}
static int appletGetFocusState(void){return focus;}
static void log_line(const char *fmt,...){
    va_list ap;va_start(ap,fmt);size_t used=strlen(messages);
    if(used<sizeof(messages)-1)vsnprintf(messages+used,sizeof(messages)-used,fmt,ap);va_end(ap);
}
static int viOpenDefaultDisplay(ViDisplay *d){int rc=next();if(!rc){d->initialized=1;display_open++;}return rc;}
static int fx_overlay_display_open(ViDisplay *d,int *borrowed){
    *borrowed=borrow_display;
    if(*borrowed){d->initialized=1;d->display_id=55;return 0;}
    return viOpenDefaultDisplay(d);
}
static int viCreateManagedLayer(const ViDisplay *d,ViLayerFlags flags,u64 aruid,u64 *id){
    assert(d->initialized&&!flags&&aruid==appletGetAppletResourceUserId());int rc=next();if(!rc){*id=99;managed_open++;}return rc;
}
static int fake_open(Service *s,int cmd,u64 id,u64 aruid,u64 *size,unsigned char *raw){
    assert(*s&&cmd==2020&&id==99&&aruid==appletGetAppletResourceUserId());int rc=next();if(rc)return rc;
    uint32_t hdr[4]={12,16,0,0},binder=37;memcpy(raw,hdr,16);memcpy(raw+24,&binder,4);
    *size=bad_parcel?27:28;layer_open++;return 0;
}
#define serviceDispatchInOut(s,cmd,in,out,...) fake_open(s,cmd,(in).id,(in).aruid,&out,parcel.raw)
static int fake_stack(Service *s,int cmd,u64 id,u32 stack){
    assert(*s&&cmd==6000&&id==99&&stack<4);int rc=next();if(!rc)stack_mask|=1u<<stack;return rc;
}
#define serviceDispatchIn(s,cmd,in) fake_stack(s,cmd,(in).id,(in).stack)
static int viGetDisplayLogicalResolution(ViDisplay *d,s32 *w,s32 *h){assert(d->initialized);*w=1920;*h=1080;return next();}
static int viSetLayerSize(ViLayer *l,int w,int h){assert(l->layer_id==99&&w==336&&h==48);return next();}
static int viSetLayerPosition(ViLayer *l,float x,float y){assert(l->layer_id==99&&x==1548&&y==138);return next();}
static int viGetZOrderCountMax(ViDisplay *d,s32 *z){assert(d->initialized);*z=100;return next();}
static int viSetLayerZ(ViLayer *l,s32 z){assert(l->layer_id==99&&z==100);return next();}
static int viSetLayerScalingMode(ViLayer *l,int m){assert(l->initialized&&m==2);return next();}
static int nwindowCreateFromLayer(NWindow *w,ViLayer *l){assert(l->layer_id==99&&l->igbp_binder_obj_id==37);int rc=next();if(!rc){w->owner=pthread_self();window_open++;}return rc;}
static int framebufferCreate(Framebuffer *f,NWindow *w,int x,int y,int fmt,int n){
    assert(pthread_equal(w->owner,pthread_self())&&x==224&&y==32&&fmt==1&&n==2);
    int rc=next();if(!rc){f->owner=pthread_self();fb_open++;}return rc;
}
static int framebufferMakeLinear(Framebuffer *f){assert(pthread_equal(f->owner,pthread_self()));return next();}
static void *framebufferBegin(Framebuffer *f,u32 *stride){assert(pthread_equal(f->owner,pthread_self()));*stride=240*4;return null_frame?NULL:pixels;}
static void framebufferEnd(Framebuffer *f){assert(pthread_equal(f->owner,pthread_self()));__atomic_add_fetch(&frames,1,__ATOMIC_RELEASE);}
static void framebufferClose(Framebuffer *f){assert(pthread_equal(f->owner,pthread_self())&&fb_open==1);fb_open--;}
static void nwindowClose(NWindow *w){assert(pthread_equal(w->owner,pthread_self())&&window_open==1);window_open--;}
static int viCloseLayer(ViLayer *l){assert(l->layer_id==99&&layer_open==1);layer_open--;memset(l,0,sizeof(*l));return 0;}
static int viDestroyManagedLayer(ViLayer *l){assert(l->layer_id==99&&managed_open==1);managed_open--;return 0;}
static void viCloseDisplay(ViDisplay *d){assert(d->initialized&&display_open==1);display_open--;}
#include "../src/runtime/fextendo_timestamp_pixels.h"
#include "../src/runtime/fextendo_overlay_layer.h"
#include "../src/runtime/fextendo_timestamp.h"
static void clean(void){assert(!display_open&&!managed_open&&!layer_open&&!window_open&&!fb_open&&__nx_vi_layer_id==7);}
int main(int argc,char **argv){
    assert(argc==3);test_root=argv[2];
    char text[32];fx_timestamp_format(text,3723456);assert(!strcmp(text,"T+ 01:02:03.4"));
    fx_timestamp_arm(0,ticks);fx_timestamp_start();assert(!step&&!fx_timestamp_created);
    fx_timestamp_arm(1,ticks);assert(!fx_timestamp_elapsed(ticks-1));ticks+=1234000000;assert(fx_timestamp_elapsed(ticks)==1234);
    null_frame=1;fx_timestamp_main(NULL);unsigned setup_steps=step;assert(stack_mask==15);clean();
    assert(fx_timestamp_font_ready);
    for(fail_at=1;fail_at<=setup_steps;fail_at++){step=0;fx_timestamp_main(NULL);assert(step>=fail_at);clean();}
    fail_at=0;borrow_display=1;fx_timestamp_main(NULL);clean();borrow_display=0;
    fail_at=0;manager=0;fx_timestamp_main(NULL);clean();manager=1;
    bad_parcel=1;fx_timestamp_main(NULL);clean();bad_parcel=0;
    unsigned char raw[32]={0};uint32_t binder;
    assert(!fx_overlay_binder(raw,sizeof(raw),33,&binder));
    uint32_t hdr[4]={0xffffffff,16,0,0};memcpy(raw,hdr,16);assert(!fx_overlay_binder(raw,sizeof(raw),32,&binder));
    hdr[0]=12;hdr[1]=0xffffffff;memcpy(raw,hdr,16);assert(!fx_overlay_binder(raw,sizeof(raw),32,&binder));
    null_frame=0;focus=0;fx_timestamp_start();assert(fx_timestamp_created);
    for(unsigned i=0;__atomic_load_n(&frames,__ATOMIC_ACQUIRE)<3&&i<1000;i++){struct timespec t={0,1000000};nanosleep(&t,NULL);}
    fx_timestamp_shutdown();assert(!fx_timestamp_created&&frames>=3&&focus_skips==1);clean();
    unsigned last=frames;fx_timestamp_shutdown();assert(frames==last);
    memset(pixels,0x5a,sizeof(pixels));fx_timestamp_pixels(&pixels[0][0],240,3723456);
    FILE *f=fopen(argv[1],"wb");assert(f);fprintf(f,"P6\n224 32\n255\n");
    unsigned aa=0;
    for(unsigned y=0;y<32;y++){
        for(unsigned x=0;x<224;x++){uint32_t p=pixels[y][x];unsigned char rgb[3]={p,p>>8,p>>16};assert(fwrite(rgb,1,3,f)==3);aa+=(p&255)>6&&(p&255)<240;}
        for(unsigned x=224;x<240;x++)assert(pixels[y][x]==0x5a5a5a5a);
    }assert(!fclose(f)&&aa>100);
    assert(strstr(messages,"overlay ready")&&strstr(messages,"overlay unavailable"));
    puts("Timestamp: own managed layer with external game layer preserved, four display/capture stacks, scaled geometry, bounded parcel parsing, all setup failure paths, AA glyphs and real-thread cleanup passed.");
}
