/* LGPL-2.1-or-later. Shared launcher/runtime keyboard preferences. */
#ifndef FEXTENDO_KEYBOARD_OPTIONS_H
#define FEXTENDO_KEYBOARD_OPTIONS_H
#include "fextendo_gamepad.h"
#define FX_KEYBOARD_SHORTCUTS 5
#define FX_KEYBOARD_HOLD_MS 600
static const char *const fx_keyboard_shortcut_names[FX_KEYBOARD_SHORTCUTS]={
    "L + R + Left Stick", "+ and -", "L + R + Plus", "ZL + ZR + Minus", "Disabled"};
struct fx_keyboard_options { int shortcut,top; };
static struct fx_keyboard_options fx_keyboard_options;
struct fx_keyboard_chord { uint64_t since; int tracking,fired; };
static uint64_t fx_keyboard_chord_mask(int choice,int kind) {
    if(choice<0||choice>=FX_KEYBOARD_SHORTCUTS-1)return 0;
    /* A horizontal Joy-Con has one +/- button and one stick. Its normalized
     * SL/SR + Stick chord remains available for every enabled choice. */
    if(kind==FX_PAD_LEFT||kind==FX_PAD_RIGHT)return FX_PAD_L|FX_PAD_R|FX_PAD_LSTICK;
    const uint64_t masks[]={FX_PAD_L|FX_PAD_R|FX_PAD_LSTICK,FX_PAD_PLUS|FX_PAD_MINUS,
        FX_PAD_L|FX_PAD_R|FX_PAD_PLUS,FX_PAD_ZL|FX_PAD_ZR|FX_PAD_MINUS};
    return masks[choice];
}
/* Only detects a request. It never suppresses gamepad input. Rearm on chord
 * release, independently of analog motion or the other player's controls. */
static int fx_keyboard_chord_poll(struct fx_keyboard_chord *s,uint64_t buttons,
                                  uint64_t mask,uint64_t now,int enabled) {
    if(!mask||(buttons&mask)!=mask){memset(s,0,sizeof(*s));return 0;}
    if(!enabled){s->fired=1;s->tracking=0;return 0;}
    if(s->fired)return 0;
    if(!s->tracking){s->tracking=1;s->since=now;return 0;}
    if(now-s->since<FX_KEYBOARD_HOLD_MS)return 0;
    s->fired=1;return 1;
}
#endif
