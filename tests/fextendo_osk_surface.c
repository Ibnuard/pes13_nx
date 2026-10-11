/* Real publisher and pixel renderer; no VI layer or fake display_show. */
#define FX_KEYBOARD_OVERLAY 1
#include <assert.h>
#include <pthread.h>
#include <stdarg.h>
#include "../src/runtime/fextendo_presets.h"
#include "../src/runtime/fextendo_renderers.h"
#include "../src/runtime/fextendo_ui.h"
#include "../src/runtime/fextendo_osk.h"
static const char *runtime_root;
#define RUNTIME_DIR runtime_root
static uint64_t now=100;
static uint64_t armGetSystemTick(void){return now;}
static uint64_t armGetSystemTickFreq(void){return 1000;}
static unsigned logs;
static void trace(const char *fmt,...){(void)fmt;logs++;}
#define FX_OSK_TRACE(...) trace(__VA_ARGS__)
typedef struct {int count;struct {int x,y;} touches[1];} HidTouchScreenState;
static int hidGetTouchScreenStates(HidTouchScreenState *s,int n){(void)s;assert(n==1);return 0;}
#include "../src/runtime/fextendo_osk_display.h"
int main(int argc,char **argv){
    assert(argc==2);runtime_root=argv[1];struct fx_osk_core s={.generation=1,.selected=24};
    struct fx_osk_frame f,old;
    assert(!fx_osk_frame_visible()&&!fx_osk_frame_get(1280,720,&f));
    assert(fx_osk_display_show(&s,0,0)==2&&fx_osk_frame_visible());
    assert(fx_osk_frame_get(1280,720,&f)&&f.width==1280&&f.height==252&&f.y==468);
    int stride=(f.width+8)*4;size_t bytes=(size_t)stride*f.height+16;
    uint32_t *pixels=malloc(bytes),*bgra=malloc(bytes);memset(pixels,0,bytes);memset(bgra,0,bytes);
    assert(fx_osk_frame_copy(&f,pixels,stride,1));assert(fx_osk_frame_copy(&f,bgra,stride,0));
    for(int y=0;y<f.height;y++)for(int x=0;x<f.width+8;x++){
        uint32_t a=pixels[y*(stride/4)+x],b=bgra[y*(stride/4)+x];
        if(x<f.width){assert(a>>24==255);assert(b==((a&0xff00ff00u)|((a&255)<<16)|((a>>16)&255)));}
        else assert(!a&&!b);
    }
    for(size_t i=bytes-16;i<bytes;i++)assert(!((unsigned char *)pixels)[i]);
    assert(!fx_osk_frame_copy(&f,pixels,10,1));
    unsigned initial_logs=logs;assert(fx_osk_display_show(&s,0,0)==2&&logs==initial_logs);
    old=f;fx_osk_frame_presented(f.session);assert(fx_osk_display_show(&s,0,0)==1);
    /* No present acknowledgement from an old session can open the new one. */
    fx_osk_display_close();assert(!fx_osk_frame_copy(&f,pixels,stride,1));
    assert(fx_osk_display_show(&s,0,0)==2);fx_osk_frame_presented(old.session);
    assert(fx_osk_display_show(&s,0,0)==2);
    assert(fx_osk_frame_get(1280,720,&f)&&f.generation!=old.generation&&f.session!=old.session);
    s.top=1;s.generation++;assert(fx_osk_display_show(&s,0,0)==2);
    assert(!fx_osk_frame_copy(&f,pixels,stride,1));
    assert(fx_osk_frame_get(1280,720,&f)&&f.y==0);fx_osk_frame_presented(f.session);
    assert(fx_osk_display_show(&s,0,0)==1);
    /* Docked and reduced-size surfaces preserve geometry, opaque pixels and padding. */
    for(int scale=1;scale<=3;scale++){
        assert(fx_osk_frame_get(640*scale,360*scale,&f)&&f.width==640*scale&&f.height==126*scale);
        size_t n=(size_t)(f.width+4)*f.height*4;
        uint32_t *q=calloc(1,n);assert(fx_osk_frame_copy(&f,q,(f.width+4)*4,1));
        for(int y=0;y<f.height;y++)for(int x=0;x<f.width+4;x++)
            assert(x<f.width?q[y*(f.width+4)+x]>>24==255:!q[y*(f.width+4)+x]);
        free(q);
    }
    fx_osk_frame_reject(f.session);assert(!fx_osk_display_show(&s,0,0)&&!fx_osk_frame_visible());
    assert(fx_osk_display_show(&s,0,0)==2);now+=3001;
    assert(!fx_osk_display_show(&s,0,0)&&!fx_osk_frame_visible());
    assert(fx_osk_display_show(&s,0,0)==2);assert(fx_osk_frame_get(1280,720,&f));
    fx_osk_frame_presented(f.session);assert(fx_osk_display_show(&s,0,0)==1);
    now+=3001;assert(!fx_osk_display_show(&s,0,0)); /* stopped presenting after first frame */
    runtime_root="/fextendo-test-missing-font";assert(!fx_osk_display_show(&s,0,0));
    assert(!fx_osk_pixels&&!fx_osk_art.font&&!fx_osk_frame_visible());
    free(pixels);free(bgra);puts("PASS: real frame publisher, RGBA/BGRA, scale/position, padding, generation race, reopen, present acknowledgement, timeout and recovery");
    return 0;
}
