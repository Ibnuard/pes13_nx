/* Model libnx ownership using real pthreads and the production launcher code. */
#include <assert.h>
#include <pthread.h>
#include <stdint.h>
#include <time.h>
#include <stdlib.h>
#include <stdarg.h>
static int mode;
#define FX_SPLASH_MS (mode>=5?2400:0)
#include "../src/runtime/fextendo_presets.h"
#include "../src/runtime/fextendo_ui.h"
typedef uint64_t u64;typedef uint32_t u32;typedef int Result;
typedef struct {int index;} PadState;
typedef struct {pthread_t owner;uint32_t *pixels;} Framebuffer;
typedef struct {int unused;} ErrorApplicationConfig;
#define R_SUCCEEDED(x) ((x)==0)
#define R_FAILED(x) ((x)!=0)
#define PIXEL_FORMAT_RGBA_8888 1
#define HidNpadStyleSet_NpadStandard 0
#define HidNpadButton_A 1
#define HidNpadButton_B 2
#define HidNpadButton_Plus 4
#define HidNpadButton_Left 8
#define HidNpadButton_Right 16
#define HidNpadButton_Up 32
#define HidNpadButton_Down 64
#define HidNpadButton_StickLLeft 128
#define HidNpadButton_StickLRight 256
#define HidNpadButton_StickLUp 512
#define HidNpadButton_StickLDown 1024
#define HidNpadButton_L 2048
#define HidNpadButton_R 4096
#define HidNpadButton_Y 8192
static const char *test_root,*test_target;static int created,closed,errors;
#define RUNTIME_DIR test_root
#define DEFAULT_TARGET test_target
static u64 armGetSystemTick(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (u64)t.tv_sec*1000000000+t.tv_nsec;}
static u64 armTicksToNs(u64 t){return t;}
static u64 armNsToTicks(u64 t){return t;}
static void svcSleepThread(u64 n){struct timespec t={n/1000000000,n%1000000000};nanosleep(&t,0);}
static int appletMainLoop(void){return 1;}
static void *nwindowGetDefault(void){return NULL;}
static int framebufferCreate(Framebuffer *f,void *w,int x,int y,int format,int count){
    (void)w;(void)format;(void)count;assert(!created++);f->owner=pthread_self();f->pixels=calloc(x*y,4);assert(f->pixels);return 0;
}
static int framebufferMakeLinear(Framebuffer *f){(void)f;return 0;}
static void *framebufferBegin(Framebuffer *f,u32 *stride){assert(pthread_equal(f->owner,pthread_self()));*stride=1280*4;return f->pixels;}
static void framebufferEnd(Framebuffer *f){assert(pthread_equal(f->owner,pthread_self()));}
static void framebufferClose(Framebuffer *f){assert(pthread_equal(f->owner,pthread_self()));assert(!closed++);free(f->pixels);}
static void padConfigureInput(int a,int b){(void)a;(void)b;}
static void padInitializeDefault(PadState *p){p->index=-1;}
static void trace_view(int frame);
static unsigned splash_seen;static int credits_seen,changelog_seen;
static void padUpdate(PadState *p){p->index++;trace_view(p->index);}
static u64 padGetButtonsDown(PadState *p){
    if(mode==4){
        static const u64 input[]={HidNpadButton_Right,0,HidNpadButton_Right,HidNpadButton_A,HidNpadButton_R,HidNpadButton_L,HidNpadButton_B,HidNpadButton_Plus};
        return p->index<8?input[p->index]:0;
    }
    if(mode==5)return p->index==2?HidNpadButton_A:p->index==8?HidNpadButton_Plus:0;
    if(mode==6)return splash_seen&&p->index>155?HidNpadButton_Plus:0;
    if(mode==3){
        static const u64 input[]={HidNpadButton_Right,HidNpadButton_A,HidNpadButton_Up,0,HidNpadButton_Up,0,HidNpadButton_Up,HidNpadButton_A,HidNpadButton_B,0,HidNpadButton_Plus};
        return p->index<11?input[p->index]:0;
    }
    if(mode==1)return p->index==0?HidNpadButton_Plus:0;
    if(mode==2)return p->index==0||p->index==2?HidNpadButton_A:p->index==4?HidNpadButton_Plus:0;
    return p->index==0?HidNpadButton_A:0;
}
static u64 padGetButtons(PadState *p){if(mode==5&&p->index>=2&&p->index<6)return HidNpadButton_A;return padGetButtonsDown(p);}
static int errorApplicationCreate(ErrorApplicationConfig *c,const char *a,const char *b){(void)c;(void)a;(void)b;return 0;}
static void errorApplicationShow(ErrorApplicationConfig *c){(void)c;errors++;}
static void log_line(const char *f,...){(void)f;}
enum fx_cue {FX_NAV,FX_CONFIRM,FX_BACK,FX_ERROR};
static int sound_open,battery_open;
static void fx_sfx_init(const char *root){(void)root;assert(!sound_open);sound_open=1;}
static void fx_music_set(int enabled){(void)enabled;}
static void fx_sfx_close(void){sound_open=0;}
static void fx_sfx_play(enum fx_cue cue,int enabled){(void)cue;(void)enabled;}
typedef int PsmChargerType;
#define PsmChargerType_Unconnected 0
static int psmInitialize(void){battery_open=1;return 0;}
static void psmExit(void){assert(battery_open);battery_open=0;}
static int psmGetBatteryChargePercentage(u32 *n){*n=82;return 0;}
static int psmGetChargerType(PsmChargerType *t){*t=0;return 0;}
static void fx_timestamp_start(void){}
static void fx_timestamp_arm(int on,uint64_t t){(void)on;(void)t;}
#include "../src/runtime/fextendo_launcher.h"
static void trace_view(int frame){
    if(fx_ui_view.splash_ms>splash_seen)splash_seen=fx_ui_view.splash_ms;
    if(fx_ui_view.screen==FX_CREDITS){credits_seen=1;if(fx_ui_view.credit_page)changelog_seen=1;}
    if(mode>=5&&frame>5)assert(!fx_boot_started);
}

int main(int argc,char **argv){
    assert(argc==4);test_root=argv[1];test_target=argv[2];mode=atoi(argv[3]);
    if(mode==3)assert(fx_apply_preset(test_root,0));
    if(mode){assert(!fx_launcher_start());assert(!fx_owned());assert(closed==1);assert(!fx_ui_created);
        if(mode==3){assert(fx_ui_view.timestamp);assert(fx_debug_timestamp(test_root));assert(fx_ui_view.screen==FX_HOME);}
        if(mode==4){assert(credits_seen&&changelog_seen);assert(fx_ui_view.screen==FX_HOME&&fx_ui_view.tile==2);assert(!fx_boot_started);}
        if(mode>=5){assert(splash_seen>2000);assert(!fx_ui_view.splash_ms);assert(!fx_boot_started);}}
    else{
        assert(fx_launcher_start());assert(!sound_open);assert(fx_owned());assert(!closed);assert(fx_boot_started);
        fx_stage("Testing loading handoff...");assert(fx_handoff());assert(!fx_owned());assert(closed==1);assert(!fx_ui_created);
        assert(fx_handoff());assert(closed==1); /* repeated acquisitions cannot rejoin */
        fx_fail("A modeled startup failure");assert(errors==1);
        assert(!fx_last_played(test_root));fx_record_first_present();assert(!fx_last_played(test_root));
        fx_history_flush();uint64_t saved=fx_last_played(test_root);assert(saved>0);
        fx_record_first_present();fx_history_flush();assert(fx_last_played(test_root)==saved);
        fx_fail("Ignored after successful first frame");assert(errors==1);
    }
    assert(!sound_open&&!battery_open);
    puts("Controller startup/cancel/error flow and one-owner framebuffer handoff passed.");return 0;
}
