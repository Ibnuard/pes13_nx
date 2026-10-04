/* File persistence/recovery, with no game or platform dependency. */
#include <assert.h>
#include "../src/runtime/fextendo_presets.h"
int main(int argc,char **argv) {
    assert(argc==2);const char *root=argv[1];char path[800],old[800];
    struct fx_keyboard_options value=fx_keyboard_options_load(root);
    assert(!value.shortcut&&!value.top);
    for(int s=0;s<FX_KEYBOARD_SHORTCUTS;s++)for(int top=0;top<2;top++){
        assert(fx_keyboard_options_save(root,(struct fx_keyboard_options){s,top}));
        value=fx_keyboard_options_load(root);assert(value.shortcut==s&&value.top==top);
    }
    assert(!fx_keyboard_options_save(root,(struct fx_keyboard_options){5,0}));
    assert(!fx_keyboard_options_save(root,(struct fx_keyboard_options){0,-1}));
    snprintf(path,sizeof(path),"%s/launcher/keyboard.ini",root);
    snprintf(old,sizeof(old),"%s/launcher/keyboard.ini.old",root);
    assert(!rename(path,old)); /* Power loss between the two renames. */
    value=fx_keyboard_options_load(root);assert(value.shortcut==4&&value.top==1);
    assert(fx_write(path,"[keyboard]\nshortcut=99\ntop=0\n",28));
    value=fx_keyboard_options_load(root);assert(value.shortcut==4&&value.top==1);
    assert(fx_keyboard_options_save(root,(struct fx_keyboard_options){1,0}));
    value=fx_keyboard_options_load(root);assert(value.shortcut==1&&!value.top);
    assert(access(old,F_OK));
    puts("PASS: all keyboard choices, invalid values, interrupted rename and corrupt primary recovery");
}
