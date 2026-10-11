/* LGPL-2.1-or-later. Group navigation shared by launcher and host tests. */
#ifndef FEXTENDO_SETTINGS_H
#define FEXTENDO_SETTINGS_H
enum fx_settings_page { FX_SETTINGS_ROOT,FX_SETTINGS_GRAPHICS,FX_SETTINGS_RENDERER,
    FX_SETTINGS_KEYBOARD,FX_SETTINGS_SHORTCUT,FX_SETTINGS_POSITION,FX_SETTINGS_AUDIO,FX_SETTINGS_MAINTENANCE,FX_SETTINGS_HOLD,FX_SETTINGS_PAGES };
static int fx_settings_rows(int page) {
    static const int counts[FX_SETTINGS_PAGES]={7,4,2,3,FX_KEYBOARD_SHORTCUTS,2,2,1,FX_KEYBOARD_HOLD_CHOICES};
    return page>=0&&page<FX_SETTINGS_PAGES?counts[page]:6;
}
static float fx_settings_scroll_target(int row,int page) {
    int max=fx_settings_rows(page)-3;if(max<0)max=0;
    int scroll=row-2;if(scroll<0)scroll=0;if(scroll>max)scroll=max;
    return scroll*116.f;
}
static void fx_settings_enter(struct fx_view *v,int page,int row) {
    v->settings_page=page;v->row=row;v->saved=0;
    v->settings_scroll=fx_settings_scroll_target(row,page);
}
static void fx_settings_back(struct fx_view *v) {
    switch(v->settings_page){
    case FX_SETTINGS_ROOT:v->screen=FX_HOME;break;
    case FX_SETTINGS_GRAPHICS:fx_settings_enter(v,FX_SETTINGS_ROOT,0);break;
    case FX_SETTINGS_RENDERER:fx_settings_enter(v,FX_SETTINGS_ROOT,1);break;
    case FX_SETTINGS_KEYBOARD:fx_settings_enter(v,FX_SETTINGS_ROOT,2);break;
    case FX_SETTINGS_AUDIO:fx_settings_enter(v,FX_SETTINGS_ROOT,3);break;
    case FX_SETTINGS_MAINTENANCE:fx_settings_enter(v,FX_SETTINGS_ROOT,6);break;
    case FX_SETTINGS_SHORTCUT:fx_settings_enter(v,FX_SETTINGS_KEYBOARD,0);break;
    case FX_SETTINGS_POSITION:fx_settings_enter(v,FX_SETTINGS_KEYBOARD,1);break;
    case FX_SETTINGS_HOLD:fx_settings_enter(v,FX_SETTINGS_KEYBOARD,2);break;
    }
}
static const char *fx_settings_title(int page) {
    static const char *const titles[]={"Settings","Graphics preset","Renderer","Keyboard","Keyboard shortcut","Keyboard position","Audio","Maintenance","Keyboard activation"};
    return titles[page];
}
static const char *fx_settings_subtitle(int page) {
    static const char *const text[]={"Choose a group to configure.","Choose the graphics preset for your next game.",
        "Choose the renderer for your next game.","Choose how to open and position the keyboard.",
        "Combos: Player 1. Capture: either controller; keyboard controls: Player 1.","You can also press Y while typing to move it.","Sounds and background music in the launcher.","Run a full installation and runtime check when needed.",
        "Choose how long to hold a combo. Capture always uses a short press."};
    return text[page];
}
static const char *fx_settings_label(const struct fx_view *v,int row) {
    static const char *const root[]={"Graphics preset","Renderer","Keyboard","Audio","Debug timestamp","Show debug launch","Maintenance"};
    static const char *const keyboard[]={"Shortcut","Position","Activation delay"};
    static const char *const audio[]={"Menu sounds","Background music"};
    switch(v->settings_page){
    case FX_SETTINGS_GRAPHICS:return fx_preset_names[row];
    case FX_SETTINGS_RENDERER:return fx_renderer_names[row];
    case FX_SETTINGS_KEYBOARD:return keyboard[row];
    case FX_SETTINGS_SHORTCUT:return fx_keyboard_shortcut_names[row];
    case FX_SETTINGS_POSITION:return row?"Top":"Bottom";
    case FX_SETTINGS_HOLD:return fx_keyboard_hold_names[row];
    case FX_SETTINGS_AUDIO:return audio[row];
    case FX_SETTINGS_MAINTENANCE:return "Check runtime";
    default:return root[row];
    }
}
static const char *fx_settings_detail(const struct fx_view *v,int row) {
    switch(v->settings_page){
    case FX_SETTINGS_ROOT:
        return row==0?fx_preset_names[v->selected]:row==1?fx_renderer_names[v->renderer]:
            row==2?"Shortcut and screen position":row==3?"Menu sounds and background music":
            row==4?"On-screen stopwatch while you play":row==5?"Add a tile for troubleshooting startup":"Check and repair the runtime";
    case FX_SETTINGS_GRAPHICS:return row==3&&!v->boot_patch?"LOCKED  /  Boot FEXTendo Patch with the updated HOME tile":fx_preset_details[row];
    case FX_SETTINGS_RENDERER:return row?"Async shader compilation  /  Alternative renderer":"Default renderer";
    case FX_SETTINGS_KEYBOARD:return row==0?fx_keyboard_shortcut_names[fx_keyboard_options.shortcut]:
        row==1?(fx_keyboard_options.top?"Top":"Bottom"):fx_keyboard_options.shortcut==FX_KEYBOARD_CAPTURE?
        "Short press (Capture)":fx_keyboard_hold_names[fx_keyboard_hold_index(fx_keyboard_options.hold_ms)];
    case FX_SETTINGS_SHORTCUT:return row==FX_KEYBOARD_DISABLED?"Open automatically in detected text fields only":
        row==FX_KEYBOARD_CAPTURE?"Either controller  /  Replaces screenshots during gameplay":"Single Joy-Con: SL + SR + Stick";
    case FX_SETTINGS_POSITION:return row?"Place the keyboard at the top of the screen":"Place the keyboard at the bottom of the screen";
    case FX_SETTINGS_HOLD:return fx_keyboard_options.shortcut==FX_KEYBOARD_CAPTURE?"Saved for button combos; Capture uses a short press":
        row?"Hold the full combo for this long":"Open as soon as the full combo is pressed";
    case FX_SETTINGS_AUDIO:return row?"Original ambient loop in the launcher":"Soft sounds for navigation and actions";
    case FX_SETTINGS_MAINTENANCE:return "Ignore saved verification and repair missing runtime files";
    default:return "";
    }
}
static int fx_settings_selected(const struct fx_view *v,int row) {
    switch(v->settings_page){
    case FX_SETTINGS_GRAPHICS:return v->selected==row;
    case FX_SETTINGS_RENDERER:return v->renderer==row;
    case FX_SETTINGS_SHORTCUT:return fx_keyboard_options.shortcut==row;
    case FX_SETTINGS_POSITION:return fx_keyboard_options.top==row;
    case FX_SETTINGS_HOLD:return fx_keyboard_options.hold_ms==(int)fx_keyboard_hold_ms[row];
    default:return 0;
    }
}
static int fx_settings_toggle(const struct fx_view *v,int row) {
    if(v->settings_page==FX_SETTINGS_ROOT&&row==4)return v->timestamp;
    if(v->settings_page==FX_SETTINGS_ROOT&&row==5)return v->debug_launch;
    if(v->settings_page==FX_SETTINGS_AUDIO)return row?v->music:v->sound;
    return -1;
}
static int fx_settings_group(const struct fx_view *v,int row) {
    return (v->settings_page==FX_SETTINGS_ROOT&&(row<4||row==6))||v->settings_page==FX_SETTINGS_KEYBOARD;
}
/* Returns failure without changing the displayed selection when storage fails. */
static int fx_settings_choose(struct fx_view *v,const char *root) {
    int row=v->row,page=v->settings_page;
    if(row<0||row>=fx_settings_rows(page))return 0;
    if(page==FX_SETTINGS_ROOT&&row==6){fx_settings_enter(v,FX_SETTINGS_MAINTENANCE,0);return 1;}
    if(page==FX_SETTINGS_ROOT&&row<4){
        static const int pages[]={FX_SETTINGS_GRAPHICS,FX_SETTINGS_RENDERER,FX_SETTINGS_KEYBOARD,FX_SETTINGS_AUDIO};
        fx_settings_enter(v,pages[row],row==0?v->selected:row==1?v->renderer:0);return 1;
    }
    if(page==FX_SETTINGS_KEYBOARD){
        static const int pages[]={FX_SETTINGS_SHORTCUT,FX_SETTINGS_POSITION,FX_SETTINGS_HOLD};
        int selected=row==0?fx_keyboard_options.shortcut:row==1?fx_keyboard_options.top:fx_keyboard_hold_index(fx_keyboard_options.hold_ms);
        fx_settings_enter(v,pages[row],selected);return 1;
    }
    if(page==FX_SETTINGS_GRAPHICS){if(row==3&&!v->boot_patch)return 0;if(!fx_apply_preset(root,row))return 0;v->selected=row;}
    else if(page==FX_SETTINGS_RENDERER){if(!fx_renderer_save(root,row))return 0;v->renderer=row;}
    else if(page==FX_SETTINGS_SHORTCUT||page==FX_SETTINGS_POSITION||page==FX_SETTINGS_HOLD){
        struct fx_keyboard_options next=fx_keyboard_options;
        if(page==FX_SETTINGS_SHORTCUT)next.shortcut=row;
        else if(page==FX_SETTINGS_POSITION)next.top=row;
        else next.hold_ms=(int)fx_keyboard_hold_ms[row];
        if(!fx_keyboard_options_save(root,next))return 0;fx_keyboard_options=next;
    }else if(page==FX_SETTINGS_AUDIO){
        if(row){if(!fx_background_music_save(root,!v->music))return 0;v->music=!v->music;}
        else{if(!fx_menu_sound_save(root,!v->sound))return 0;v->sound=!v->sound;}
    }else if(page==FX_SETTINGS_ROOT&&row==4){
        if(!fx_debug_timestamp_save(root,!v->timestamp))return 0;v->timestamp=!v->timestamp;
    }else if(page==FX_SETTINGS_ROOT&&row==5){
        if(!fx_debug_launch_save(root,!v->debug_launch))return 0;v->debug_launch=!v->debug_launch;
        if(!v->debug_launch&&v->tile==4)v->tile=0;
    }else return 0;
    v->saved=1;return 1;
}
#endif
