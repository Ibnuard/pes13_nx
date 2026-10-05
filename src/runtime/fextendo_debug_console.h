/* LGPL-2.1-or-later. Startup view on the existing launcher framebuffer.
 * No independent layer, worker, controller shortcut or in-game polling. */
#ifndef FEXTENDO_DEBUG_CONSOLE_H
#define FEXTENDO_DEBUG_CONSOLE_H
#include "fextendo_launch_debug.h"
static void fx_debug_draw(struct fx_canvas *c,const struct fx_debug_snapshot *snap){
    fx_rect(c,0,0,FX_W,FX_H,FX_COLOR(0,0,0),255);
    fx_text(c,24,15,"FEXTendo | Debug launch | Startup",1,FX_WHITE);
    char status[128];snprintf(status,sizeof(status),"%llu.%03llu s   |   Closes when game takes screen   |   Log: fex-runtime.log   |   dropped %u",
        (unsigned long long)(snap->elapsed_ms/1000),(unsigned long long)(snap->elapsed_ms%1000),snap->dropped);
    fx_text(c,24,49,status,3,FX_MUTED);
    unsigned first=snap->count>27?snap->count-27:0;
    c->clip_left=24;c->clip_right=1256;
    for(unsigned i=first;i<snap->count;i++)fx_text(c,24,83+(int)(i-first)*22,snap->lines[i],3,FX_WHITE);
    c->clip_left=c->clip_right=0;
}
#endif
