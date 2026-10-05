/* Compile with ASan/UBSan. The screenshots use the production C renderer. */
#include <assert.h>
#include "../src/runtime/fextendo_presets.h"
#include "../src/runtime/fextendo_renderers.h"
#include "../src/runtime/fextendo_ui.h"
#define FX_LAUNCH_DEBUG_NOW() 0ull
#define FX_DEBUG_PIXELS_ONLY 1
#include "../src/runtime/fextendo_debug_console.h"
int main(int argc,char **argv) {
    struct fx_art art;struct fx_view v={.screen=FX_HOME};char path[1024];int i,x,y;
    assert(argc==3);assert(fx_art_load(&art,argv[1]));
    uint32_t *buffer=calloc(1296*720,4);assert(buffer);
    struct fx_canvas c={buffer,1296,&art};
    for(i=0;i<28;i++){
        v.settings_page=FX_SETTINGS_ROOT;
        v.screen=i<2?FX_HOME:i<4?FX_SETTINGS:i==4?FX_LOADING:FX_FAILED;
        v.tile=i==1;v.tile_mix=v.tile;v.sound=1;v.battery=82;v.wall_time=1800000000;v.last_played=v.wall_time-7200;v.row=i==3?3:0;v.selected=0;v.frame=32;v.saved=i==3;
        v.fatal=i==6;v.message=i==4?"Loading game files...":"Could not save the preset. Check the SD card.";
        if(i==7){v.screen=FX_HOME;v.frame=65;}
        if(i==8){v.screen=FX_SETTINGS;v.row=4;v.timestamp=1;}
        v.splash_ms=i==9?600:0;
        if(i>=10){v.screen=i==10?FX_HOME:FX_CREDITS;v.tile=2;v.tile_mix=2;v.credit_page=i==12;}
        if(i>=13){v.screen=FX_SETTINGS;v.settings_page=FX_SETTINGS_RENDERER;v.row=(i-13)%2;v.renderer=v.row;}
        if(i==15){v.screen=FX_HOME;v.tile=3;v.tile_mix=3;}
        if(i>=16){
            v.screen=FX_GAMEPAD;v.row=i==17;v.players=2;v.message=NULL;v.pad_test=i==17;
            v.pads[0]=fx_pad_normalize(i==16?FX_PAD_FULL:FX_PAD_LEFT,1,FX_PAD_DOWN|FX_PAD_SL,0,-24000,0,0);
            v.pads[1]=fx_pad_normalize(FX_PAD_RIGHT,i!=18,FX_PAD_X|FX_PAD_SR,0,0,24000,0);
        }
        if(i>=20&&i<25){
            static const int pages[]={FX_SETTINGS_KEYBOARD,FX_SETTINGS_SHORTCUT,FX_SETTINGS_POSITION,FX_SETTINGS_GRAPHICS,FX_SETTINGS_AUDIO};
            v.screen=FX_SETTINGS;v.settings_page=pages[i-20];v.row=i==21?1:0;
            fx_keyboard_options.shortcut=1;fx_keyboard_options.top=1;
        }
        if(i==25){v.screen=FX_SETTINGS;v.settings_page=FX_SETTINGS_ROOT;v.row=5;v.debug_launch=1;}
        if(i==26){v.screen=FX_HOME;v.tile=4;v.tile_mix=4;v.debug_launch=1;}
        v.settings_scroll=fx_settings_scroll_target(v.row,v.settings_page);
        fx_render(&c,&v);
        if(i==27){
            struct fx_debug_snapshot snap={.count=6,.elapsed_ms=7320};
            const char *lines[]={"[0.000] [STARTUP] FEXTendo 0.3.8-r3 / startup console / debug files enabled",
                "[0.002] [MEMORY] mode=32-bit no-alias base=200000 span=ffe00000 alias=0",
                "[0.004] [STARTUP] verifying renderer files...","[0.932] [STARTUP] renderer ready=1; verifying game settings...",
                "[1.064] [INIT] Wine NLS/environment ready","[7.310] [ATTACH] loading C:\\windows\\system32\\libwow64fex.dll"};
            for(int row=0;row<6;row++)snprintf(snap.lines[row],sizeof(snap.lines[row]),"%s",lines[row]);
            fx_debug_draw(&c,&snap);
        }
        if(i==19)fx_gamepad_pause(&c,v.pads,2,1,0,1);
        snprintf(path,sizeof(path),"%s/screen-%d.ppm",argv[2],i);FILE *f=fopen(path,"wb");assert(f);
        fprintf(f,"P6\n1280 720\n255\n");
        for(y=0;y<720;y++){
            for(x=0;x<1280;x++){uint32_t p=buffer[y*1296+x];unsigned char rgb[3]={p,p>>8,p>>16};fwrite(rgb,1,3,f);}
            for(x=1280;x<1296;x++)assert(buffer[y*1296+x]==0);
        }assert(!fclose(f));
    }
    /* Idle tiles and disabled Play must not change when the glow phase changes. */
    uint32_t *snapshot=malloc(1296*720*4);assert(snapshot);
    /* Outside Test Controls, input cannot animate either controller card. */
    v.screen=FX_GAMEPAD;v.pad_test=0;v.row=0;v.message=NULL;
    v.pads[0]=fx_pad_normalize(FX_PAD_FULL,1,0,0,0,0,0);
    v.pads[1]=fx_pad_normalize(FX_PAD_RIGHT,1,0,0,0,0,0);
    fx_render(&c,&v);memcpy(snapshot,buffer,1296*720*4);
    v.pads[0]=fx_pad_normalize(FX_PAD_FULL,1,0xffff,32000,-32000,-25000,25000);
    v.pads[1]=fx_pad_normalize(FX_PAD_RIGHT,1,FX_PAD_X|FX_PAD_SR,0,0,32000,16000);
    fx_render(&c,&v);assert(!memcmp(snapshot,buffer,1296*720*4));
    v.pad_test=1;fx_render(&c,&v);unsigned test_changes=0;
    for(y=280;y<505;y++)for(x=64;x<1216;x++)test_changes+=snapshot[y*1296+x]!=buffer[y*1296+x];
    assert(test_changes>500);
    v.pad_test=0;fx_render(&c,&v);assert(!memcmp(snapshot,buffer,1296*720*4));
    v.pads[1].connected=0;fx_render(&c,&v);assert(memcmp(snapshot,buffer,1296*720*4));
    v.debug_launch=0;v.screen=FX_HOME;v.splash_ms=0;v.tile=0;v.tile_mix=0;v.frame=0;fx_render(&c,&v);
    memcpy(snapshot,buffer,1296*720*4);v.frame=140;fx_render(&c,&v);
    unsigned active_changed=0;
    for(y=230;y<530;y++)for(x=915;x<1248;x++)assert(snapshot[y*1296+x]==buffer[y*1296+x]);
    for(y=538;y<622;y++)for(x=60;x<340;x++)active_changed+=snapshot[y*1296+x]!=buffer[y*1296+x];
    assert(active_changed>100);
    v.tile=1;v.tile_mix=1;v.frame=0;fx_render(&c,&v);memcpy(snapshot,buffer,1296*720*4);
    v.frame=140;fx_render(&c,&v);
    for(y=538;y<622;y++)for(x=60;x<340;x++)assert(snapshot[y*1296+x]==buffer[y*1296+x]);
    for(y=230;y<530;y++)for(x=645;x<855;x++)assert(snapshot[y*1296+x]==buffer[y*1296+x]);
    /* Loading ignores menu/stage text; only the small spinner animates. */
    v.screen=FX_LOADING;v.frame=0;fx_render(&c,&v);memcpy(snapshot,buffer,1296*720*4);
    v.frame=20;v.tile=0;v.message="New startup stage";fx_render(&c,&v);active_changed=0;
    for(y=0;y<720;y++)for(x=0;x<1280;x++){
        if(x>=618&&x<=662&&y>=440&&y<=484)active_changed+=snapshot[y*1296+x]!=buffer[y*1296+x];
        else assert(snapshot[y*1296+x]==buffer[y*1296+x]);
    }
    assert(active_changed>10);
    /* Splash really moves/reveals, instead of delaying a static bitmap. */
    v.screen=FX_HOME;v.splash_ms=FX_SPLASH_MS-100;fx_render(&c,&v);memcpy(snapshot,buffer,1296*720*4);
    v.splash_ms=FX_SPLASH_MS-900;fx_render(&c,&v);active_changed=0;
    for(y=240;y<470;y++)for(x=330;x<950;x++)active_changed+=snapshot[y*1296+x]!=buffer[y*1296+x];
    assert(active_changed>1000);
    v.splash_ms=0;v.screen=FX_CREDITS;v.credit_page=0;fx_render(&c,&v);memcpy(snapshot,buffer,1296*720*4);
    v.credit_page=1;fx_render(&c,&v);active_changed=0;
    for(y=100;y<625;y++)for(x=400;x<1220;x++)active_changed+=snapshot[y*1296+x]!=buffer[y*1296+x];
    assert(active_changed>1000);free(snapshot);
    struct fx_light orbit=fx_orbit(240,58,29,0),cycle=fx_orbit(240,58,29,360);
    assert(orbit.x==cycle.x&&orbit.y==cycle.y);
    /* Interrupted focus changes must remain continuous and converge in time. */
    v.tile_mix=0;v.tile=1;fx_motion_step(&v,33);float first=v.tile_mix;
    assert(first>0&&first<1);v.tile=0;fx_motion_step(&v,33);assert(v.tile_mix<first&&v.tile_mix>0);
    v.tile=1;for(i=0;i<20;i++)fx_motion_step(&v,33);assert(v.tile_mix==1);
    v.tile=2;for(i=0;i<25;i++)fx_motion_step(&v,33);assert(v.tile_mix==2);
    for(int page=0;page<FX_SETTINGS_PAGES;page++)for(int row=0;row<fx_settings_rows(page);row++){
        v.settings_page=page;v.row=row;for(i=0;i<25;i++)fx_motion_step(&v,33);
        assert(v.settings_scroll==fx_settings_scroll_target(row,page));
        float top=row*116-v.settings_scroll;
        assert(top>=0&&top+100<=332);
    }
    /* A mid-scroll row cannot draw into the title or fixed footer. */
    uint32_t before=buffer[180*1296+450],after=buffer[600*1296+450];
    c.clip_top=204;c.clip_bottom=582;
    fx_round(&c,412,170,766,450,14,FX_WHITE,255);
    fx_text(&c,435,170,"Clipped",1,FX_WHITE);
    assert(buffer[180*1296+450]==before&&buffer[600*1296+450]==after);
    c.clip_top=c.clip_bottom=0;
    fx_art_free(&art);free(buffer);
    for(i=0;i<4;i++){
        unsigned char data[852],expected[852],custom[852];
        /* Existing canonical DirectInput settings must migrate to XInput,
         * preserving keyboard/DirectInput bindings and all unrelated flags. */
        snprintf(path,sizeof(path),"%s%s",argv[1],fx_targets[0]);assert(fx_read(path,custom,852)==852);
        custom[15]&=~2;custom[340]=(unsigned char)(40+i);custom[480]=(unsigned char)(60+i);
        uint16_t custom_crc=fx_crc(custom);custom[12]=custom_crc;custom[13]=custom_crc>>8;
        assert(fx_write(path,custom,852));
        assert(fx_apply_preset(argv[1],i));assert(fx_selected(argv[1])==i);
        for(x=0;x<3;x++){
            snprintf(path,sizeof(path),"%s%s",argv[1],fx_targets[x]);assert(fx_read(path,data,852)==852);
            assert(fx_valid_settings(data,852));assert(data[14]&1);assert(fx_u32(data+24)==1);
            assert(data[15]&2);assert(data[15]==(custom[15]|2));
            assert(!memcmp(data+32,custom+32,852-32));
            assert(fx_u32(data+16)==(i==2?960:1280));assert(fx_u32(data+20)==(i==2?540:720));
            if(!x)memcpy(expected,data,852);else assert(!memcmp(expected,data,852));
        }
        /* Controller data from the canonical KONAMI file must win next time. */
        snprintf(path,sizeof(path),"%s%s",argv[1],fx_targets[0]);data[340]=42;
        uint16_t crc=fx_crc(data);data[12]=crc;data[13]=crc>>8;assert(fx_write(path,data,852));
        assert(fx_apply_preset(argv[1],i));assert(fx_read(path,data,852)==852&&data[340]==42);
    }
    assert(!fx_apply_preset(argv[1],-1));assert(!fx_apply_preset(argv[1],4));
    assert(fx_menu_sound(argv[1]));assert(fx_menu_sound_save(argv[1],0));assert(!fx_menu_sound(argv[1]));
    assert(fx_menu_sound_save(argv[1],1));assert(fx_menu_sound(argv[1]));
    assert(fx_background_music(argv[1]));assert(fx_background_music_save(argv[1],0));assert(!fx_background_music(argv[1]));
    assert(fx_background_music_save(argv[1],1));assert(fx_background_music(argv[1]));
    assert(!fx_last_played(argv[1]));assert(fx_last_played_save(argv[1],1800000000));assert(fx_last_played(argv[1])==1800000000);
    char relative[48];
    fx_last_played_label(relative,0,1800000000);assert(!strcmp(relative,"Never"));
    fx_last_played_label(relative,1800000000,1799999999);assert(!strcmp(relative,"Recently"));
    fx_last_played_label(relative,1800000000,1800000059);assert(!strcmp(relative,"Just now"));
    fx_last_played_label(relative,1800000000,1800000060);assert(!strcmp(relative,"1 minute ago"));
    fx_last_played_label(relative,1800000000,1800007200);assert(!strcmp(relative,"2 hours ago"));
    fx_last_played_label(relative,1800000000,1800086400);assert(!strcmp(relative,"1 day ago"));
    assert(!fx_last_played_save(argv[1],0));assert(fx_last_played(argv[1])==1800000000);
    snprintf(path,sizeof(path),"%s/launcher/last-played.txt",argv[1]);assert(fx_write(path,"99999999999999999999999\n",24));assert(!fx_last_played(argv[1]));
    assert(!unlink(path));
    assert(!fx_debug_timestamp(argv[1]));assert(fx_debug_timestamp_save(argv[1],1));assert(fx_debug_timestamp(argv[1]));
    assert(fx_debug_timestamp_save(argv[1],0));assert(!fx_debug_timestamp(argv[1]));
    /* Real navigation + persistence: entering groups must not apply a choice;
     * B goes back one level and retains the selected parent row. */
    v=(struct fx_view){.screen=FX_SETTINGS,.selected=2,.renderer=1,.sound=1,.music=1};
    fx_settings_enter(&v,FX_SETTINGS_ROOT,0);
    assert(fx_settings_choose(&v,argv[1]));assert(v.settings_page==FX_SETTINGS_GRAPHICS&&v.row==2&&!v.saved);
    v.row=0;assert(fx_settings_choose(&v,argv[1]));assert(v.selected==0&&fx_selected(argv[1])==0&&v.saved);
    v.row=1;assert(!fx_settings_choose(&v,"/dev/null/fextendo-test"));assert(v.selected==0);
    fx_settings_back(&v);assert(v.settings_page==FX_SETTINGS_ROOT&&v.row==0);
    v.row=1;assert(fx_settings_choose(&v,argv[1]));assert(v.settings_page==FX_SETTINGS_RENDERER&&v.row==1);
    v.row=0;assert(fx_settings_choose(&v,argv[1]));assert(v.renderer==0);
    fx_settings_back(&v);assert(v.settings_page==FX_SETTINGS_ROOT&&v.row==1);
    v.row=2;assert(fx_settings_choose(&v,argv[1]));assert(v.settings_page==FX_SETTINGS_KEYBOARD);
    assert(fx_settings_choose(&v,argv[1]));assert(v.settings_page==FX_SETTINGS_SHORTCUT&&v.row==1);
    v.row=2;assert(fx_settings_choose(&v,argv[1]));assert(fx_keyboard_options_load(argv[1]).shortcut==2);
    v.row=3;assert(!fx_settings_choose(&v,"/dev/null/fextendo-test"));assert(fx_keyboard_options.shortcut==2);
    fx_settings_back(&v);assert(v.settings_page==FX_SETTINGS_KEYBOARD&&v.row==0);
    v.row=1;assert(fx_settings_choose(&v,argv[1]));assert(v.settings_page==FX_SETTINGS_POSITION&&v.row==1);
    v.row=0;assert(fx_settings_choose(&v,argv[1]));assert(!fx_keyboard_options_load(argv[1]).top);
    fx_settings_back(&v);assert(v.settings_page==FX_SETTINGS_KEYBOARD&&v.row==1);
    fx_settings_back(&v);assert(v.settings_page==FX_SETTINGS_ROOT&&v.row==2);
    v.row=3;assert(fx_settings_choose(&v,argv[1]));assert(v.settings_page==FX_SETTINGS_AUDIO);
    assert(fx_settings_choose(&v,argv[1]));assert(!v.sound&&!fx_menu_sound(argv[1]));
    v.row=1;assert(fx_settings_choose(&v,argv[1]));assert(!v.music&&!fx_background_music(argv[1]));
    fx_settings_back(&v);assert(v.settings_page==FX_SETTINGS_ROOT&&v.row==3);
    v.row=4;assert(fx_settings_choose(&v,argv[1]));assert(v.timestamp&&fx_debug_timestamp(argv[1]));
    v.row=5;assert(!fx_debug_launch(argv[1]));assert(fx_settings_choose(&v,argv[1]));
    assert(v.debug_launch&&fx_debug_launch(argv[1])&&fx_settings_toggle(&v,5)==1);
    assert(!fx_settings_choose(&v,"/dev/null/fextendo-test"));assert(v.debug_launch);
    v.tile=4;assert(fx_settings_choose(&v,argv[1]));assert(!v.debug_launch&&!fx_debug_launch(argv[1])&&!v.tile);
    fx_settings_back(&v);assert(v.screen==FX_HOME);
    puts("Nested Settings: group navigation, one-level Back, saved choices and storage failure passed.");
    puts("Production renderer, padded stride, four presets, checksums and canonical controller preservation passed.");
    return 0;
}
