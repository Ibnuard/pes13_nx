#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
typedef int Result;
typedef struct {uint64_t display_id;int initialized;} ViDisplay;
#define R_SUCCEEDED(x) ((x)==0)
static unsigned opens;static int error;
Result __real_viOpenDisplay(const char *name,ViDisplay *d){(void)name;opens++;if(error)return error;d->initialized=1;d->display_id=42;return 0;}
Result __wrap_viOpenDisplay(const char *name,ViDisplay *d);
static Result viOpenDefaultDisplay(ViDisplay *d){return __wrap_viOpenDisplay("Default",d);}
#include "../src/runtime/fextendo_display.h"
int main(void){
    ViDisplay game={0},overlay={0};int borrowed;
    error=0x1272;assert(fx_overlay_display_open(&overlay,&borrowed)==error&&!borrowed&&!fx_default_display_ready);
    error=0;assert(!__wrap_viOpenDisplay("Default",&game));assert(opens==2);
    error=0x1272; /* Opening Default twice would fail on this service. */
    for(int i=0;i<5;i++){
        assert(!fx_overlay_display_open(&overlay,&borrowed)&&borrowed);
        assert(overlay.display_id==game.display_id&&overlay.initialized&&opens==2);
        memset(&overlay,0,sizeof(overlay));assert(game.initialized);
    }
    puts("Display: captures libnx default display, avoids duplicate open 0x1272, borrows without owning game resources, preserves real setup failures.");
}
