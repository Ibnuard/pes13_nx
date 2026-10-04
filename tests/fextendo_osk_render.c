/* Compact surface bounds and screenshots from the shipped C renderer. */
#define FX_KEYBOARD_OVERLAY 1
#include <assert.h>
#include "../src/runtime/fextendo_presets.h"
#include "../src/runtime/fextendo_renderers.h"
#include "../src/runtime/fextendo_ui.h"
#include "../src/runtime/fextendo_osk.h"
#include "../src/runtime/fextendo_osk_ui.h"
int main(int argc,char **argv){
    assert(argc==3);struct fx_art art={0};assert(fx_font_load(&art,argv[1]));
    uint32_t *pixels=calloc(1296*FX_OSK_HEIGHT,4);assert(pixels);
    struct fx_canvas canvas={.pixels=pixels,.stride=1296,.art=&art,.clip_bottom=FX_OSK_HEIGHT};
    struct fx_osk_core state={.armed=1,.selected=24};
    for(int n=0;n<5;n++){
        state.shift=n==1;state.full=n==3;state.closing=n==4;
        state.selected=n==2?FX_OSK_CELLS-1:24;
        fx_osk_draw(&canvas,&state,n%2,n==2);
        char path[1024];snprintf(path,sizeof(path),"%s/keyboard-%d.ppm",argv[2],n);
        FILE *f=fopen(path,"wb");assert(f);fprintf(f,"P6\n1280 %d\n255\n",FX_OSK_HEIGHT);
        for(int y=0;y<FX_OSK_HEIGHT;y++){
            for(int x=0;x<FX_W;x++){
                uint32_t pixel=pixels[y*1296+x];unsigned char rgb[3]={pixel,pixel>>8,pixel>>16};
                assert(fwrite(rgb,1,3,f)==3);
            }
            for(int x=FX_W;x<1296;x++)assert(!pixels[y*1296+x]);
        }
        assert(!fclose(f));
    }
    for(int i=0;i<FX_OSK_CELLS;i++){
        int x,y,w;fx_osk_bounds(i,&x,&y,&w);
        assert(x>=0&&x+w<FX_W&&y>=0&&y+FX_OSK_KEY_HEIGHT<FX_OSK_HEIGHT);
        assert(fx_osk_hit(x+w/2,y+FX_OSK_KEY_HEIGHT/2)==i);
    }
    assert(fx_osk_hit(1279,FX_OSK_HEIGHT-1)==-1);free(pixels);
    pixels=calloc(1296*FX_H,4);assert(pixels);canvas.pixels=pixels;canvas.clip_bottom=FX_H;
    struct fx_pad_sample pads[2]={fx_pad_normalize(FX_PAD_FULL,1,0,0,0,0,0),fx_pad_normalize(FX_PAD_RIGHT,1,0,0,0,0,0)};
    fx_gamepad_pause(&canvas,pads,2,1,0,1);
    char path[1024];snprintf(path,sizeof(path),"%s/keyboard-pause.ppm",argv[2]);FILE *f=fopen(path,"wb");assert(f);
    fprintf(f,"P6\n1280 720\n255\n");
    for(int y=0;y<FX_H;y++){
        for(int x=0;x<FX_W;x++){
            uint32_t pixel=pixels[y*1296+x];unsigned char rgb[3]={pixel,pixel>>8,pixel>>16};
            assert(fwrite(rgb,1,3,f)==3);
        }
        for(int x=FX_W;x<1296;x++)assert(!pixels[y*1296+x]);
    }
    assert(!fclose(f));free(pixels);free(art.font);
    puts("PASS: compact renderer bounds, stride guards, labels and touch hit targets");
    return 0;
}
