/* Exercise the production overlay with modeled VI calls and real pthreads. */
#include <assert.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <time.h>
typedef uint64_t u64;
typedef uint32_t u32;
typedef int32_t s32;
typedef int Result;
typedef struct { int initialized; } ViDisplay;
typedef struct { int initialized; u64 layer_id; } ViLayer;
typedef struct { pthread_t owner; } NWindow;
typedef struct { pthread_t owner; } Framebuffer;
#define R_FAILED(x) ((x)!=0)
#define PIXEL_FORMAT_RGBA_8888 1
#define ViScalingMode_None 0
#define AppletFocusState_InFocus 1
u64 __nx_vi_layer_id;
static unsigned step,fail_at,display_open,layer_open,window_open,fb_open;
static unsigned frames,focus_skips;
static u64 ticks=1000000000;
static int focus=1,null_frame;
static uint32_t pixels[32][240];
static char messages[8192];
static int next(void) { return ++step==fail_at ? 42:0; }
static u64 armGetSystemTick(void) { return __atomic_load_n(&ticks,__ATOMIC_RELAXED); }
static u64 armTicksToNs(u64 v) { return v; }
static void svcSleepThread(u64 n) {
    __atomic_add_fetch(&ticks,n,__ATOMIC_RELAXED);
    if(!focus){focus_skips++;focus=1;}
    struct timespec t={0,1000000};nanosleep(&t,NULL);
}
static int appletGetFocusState(void) { return focus; }
static void log_line(const char *fmt,...) {
    va_list ap;va_start(ap,fmt);
    vsnprintf(messages+strlen(messages),sizeof(messages)-strlen(messages),fmt,ap);
    va_end(ap);
}
static int viOpenDefaultDisplay(ViDisplay *d) {
    int rc=next();if(!rc){d->initialized=1;display_open++;}return rc;
}
static int viCreateLayer(ViDisplay *d,ViLayer *l) {
    assert(d->initialized);int rc=next();
    if(!rc){l->initialized=1;l->layer_id=99;layer_open++;}return rc;
}
static int viSetLayerSize(ViLayer *l,int w,int h) {assert(l->layer_id==99&&w==224&&h==32);return next();}
static int viSetLayerPosition(ViLayer *l,float x,float y) {assert(l->layer_id==99&&x==1032&&y==78);return next();}
static int viGetZOrderCountMax(ViDisplay *d,s32 *z) {assert(d->initialized);*z=100;return next();}
static int viSetLayerZ(ViLayer *l,s32 z) {assert(l->layer_id==99&&z==100);return next();}
static int viSetLayerScalingMode(ViLayer *l,int m) {assert(l->initialized&&m==0);return next();}
static int nwindowCreateFromLayer(NWindow *w,ViLayer *l) {
    assert(l->layer_id==99);int rc=next();if(!rc){w->owner=pthread_self();window_open++;}return rc;
}
static int framebufferCreate(Framebuffer *f,NWindow *w,int x,int y,int fmt,int n) {
    assert(pthread_equal(w->owner,pthread_self())&&x==224&&y==32&&fmt==1&&n==2);
    int rc=next();if(!rc){f->owner=pthread_self();fb_open++;}return rc;
}
static int framebufferMakeLinear(Framebuffer *f) {assert(pthread_equal(f->owner,pthread_self()));return next();}
static void *framebufferBegin(Framebuffer *f,u32 *stride) {
    assert(pthread_equal(f->owner,pthread_self()));*stride=240*4;return null_frame?NULL:pixels;
}
static void framebufferEnd(Framebuffer *f) {assert(pthread_equal(f->owner,pthread_self()));__atomic_add_fetch(&frames,1,__ATOMIC_RELEASE);}
static void framebufferClose(Framebuffer *f) {assert(pthread_equal(f->owner,pthread_self())&&fb_open==1);fb_open--;}
static void nwindowClose(NWindow *w) {assert(pthread_equal(w->owner,pthread_self())&&window_open==1);window_open--;}
static void viCloseLayer(ViLayer *l) {assert(l->layer_id==99&&layer_open==1);layer_open--;}
static void viCloseDisplay(ViDisplay *d) {assert(d->initialized&&display_open==1);display_open--;}
#include "../src/runtime/fextendo_timestamp_pixels.h"
#include "../src/runtime/fextendo_timestamp.h"
static void clean(void) {assert(!display_open&&!layer_open&&!window_open&&!fb_open);}
int main(int argc,char **argv) {
    char text[32];fx_timestamp_format(text,3723456);assert(!strcmp(text,"T+ 01:02:03.4"));
    fx_timestamp_format(text,0);assert(!strcmp(text,"T+ 00:00:00.0"));
    memset(pixels,0x5a,sizeof(pixels));fx_timestamp_pixels(&pixels[0][0],240,3723456);
    for(unsigned y=0;y<32;y++)for(unsigned x=224;x<240;x++)assert(pixels[y][x]==0x5a5a5a5a);
    if(argc==2){
        FILE *f=fopen(argv[1],"wb");assert(f);fprintf(f,"P6\n224 32\n255\n");
        for(unsigned y=0;y<32;y++)for(unsigned x=0;x<224;x++){
            uint32_t p=pixels[y][x];unsigned char rgb[3]={p,p>>8,p>>16};assert(fwrite(rgb,1,3,f)==3);
        }assert(!fclose(f));
    }
    fx_timestamp_arm(0,ticks);fx_timestamp_start();assert(!step&&!fx_timestamp_created);
    size_t logged=strlen(messages);fx_timestamp_report();assert(strlen(messages)==logged);
    fx_timestamp_arm(1,ticks);assert(!fx_timestamp_elapsed(ticks-1));ticks+=1234000000;
    assert(fx_timestamp_elapsed(ticks)==1234);fx_timestamp_report();assert(strstr(messages,"elapsed_ms=1234"));
    __nx_vi_layer_id=7;fx_timestamp_main(NULL);assert(!step);clean();__nx_vi_layer_id=0;
    for(fail_at=1;fail_at<=10;fail_at++){step=0;fx_timestamp_main(NULL);assert(step==fail_at);clean();}
    fail_at=0;step=0;null_frame=1;fx_timestamp_main(NULL);assert(step==10);clean();null_frame=0;
    focus=0;fx_timestamp_start();assert(fx_timestamp_created);
    for(unsigned i=0;__atomic_load_n(&frames,__ATOMIC_ACQUIRE)<3&&i<1000;i++){
        struct timespec t={0,1000000};nanosleep(&t,NULL);
    }
    fx_timestamp_shutdown();assert(!fx_timestamp_created&&frames>=3&&focus_skips==1);clean();
    unsigned last=frames;fx_timestamp_shutdown();assert(frames==last);
    assert(strstr(messages,"overlay ready")&&strstr(messages,"overlay unavailable"));
    puts("Timestamp: formatting/stride, origin, OFF, external-layer guard, ten failure paths, focus and real-thread cleanup passed.");
}
