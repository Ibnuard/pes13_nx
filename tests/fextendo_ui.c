/* Compile with ASan/UBSan. The screenshots use the production C renderer. */
#include <assert.h>
#include "../src/runtime/fextendo_presets.h"
#include "../src/runtime/fextendo_ui.h"
int main(int argc,char **argv) {
    struct fx_art art;struct fx_view v={.screen=FX_HOME};char path[1024];int i,x,y;
    assert(argc==3);assert(fx_art_load(&art,argv[1]));
    uint32_t *buffer=calloc(1296*720,4);assert(buffer);
    struct fx_canvas c={buffer,1296,&art};
    for(i=0;i<9;i++){
        v.screen=i<2?FX_HOME:i<4?FX_SETTINGS:i==4?FX_LOADING:FX_FAILED;
        v.tile=i==1;v.row=i==3?3:0;v.selected=0;v.frame=32;v.saved=i==3;
        v.fatal=i==6;v.message=i==4?"Loading game files...":"Could not save the preset. Check the SD card.";
        if(i==7){v.screen=FX_HOME;v.frame=65;}
        if(i==8){v.screen=FX_SETTINGS;v.row=4;v.timestamp=1;}
        fx_render(&c,&v);
        snprintf(path,sizeof(path),"%s/screen-%d.ppm",argv[2],i);FILE *f=fopen(path,"wb");assert(f);
        fprintf(f,"P6\n1280 720\n255\n");
        for(y=0;y<720;y++){
            for(x=0;x<1280;x++){uint32_t p=buffer[y*1296+x];unsigned char rgb[3]={p,p>>8,p>>16};fwrite(rgb,1,3,f);}
            for(x=1280;x<1296;x++)assert(buffer[y*1296+x]==0);
        }assert(!fclose(f));
    }
    fx_art_free(&art);free(buffer);
    for(i=0;i<4;i++){
        unsigned char data[852],expected[852];
        assert(fx_apply_preset(argv[1],i));assert(fx_selected(argv[1])==i);
        for(x=0;x<3;x++){
            snprintf(path,sizeof(path),"%s%s",argv[1],fx_targets[x]);assert(fx_read(path,data,852)==852);
            assert(fx_valid_settings(data,852));assert(data[14]&1);assert(fx_u32(data+24)==1);
            assert(fx_u32(data+16)==(i==2?960:1280));assert(fx_u32(data+20)==(i==2?540:720));
            if(!x)memcpy(expected,data,852);else assert(!memcmp(expected,data,852));
        }
        /* Controller data from the canonical KONAMI file must win next time. */
        snprintf(path,sizeof(path),"%s%s",argv[1],fx_targets[0]);data[340]=42;
        uint16_t crc=fx_crc(data);data[12]=crc;data[13]=crc>>8;assert(fx_write(path,data,852));
        assert(fx_apply_preset(argv[1],i));assert(fx_read(path,data,852)==852&&data[340]==42);
    }
    assert(!fx_apply_preset(argv[1],-1));assert(!fx_apply_preset(argv[1],4));
    assert(!fx_debug_timestamp(argv[1]));assert(fx_debug_timestamp_save(argv[1],1));assert(fx_debug_timestamp(argv[1]));
    assert(fx_debug_timestamp_save(argv[1],0));assert(!fx_debug_timestamp(argv[1]));
    puts("Production renderer, padded stride, four presets, checksums and canonical controller preservation passed.");
    return 0;
}
