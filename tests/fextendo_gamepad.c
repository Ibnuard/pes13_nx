/* Native host regression: real normalization and original Wine XInput mapper. */
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include "windef.h"
#include "winbase.h"
#include "xinput.h"
#include "nx_pad.h"
#include "../src/runtime/fextendo_gamepad.h"
int main(void) {
    struct fx_pad_sample p;
    const int raw[][2]={{0,20000},{20000,0},{0,-20000},{-20000,0},{13000,-17000}};
    const int left[][2]={{-20000,0},{0,20000},{20000,0},{0,-20000},{17000,13000}};
    const int right[][2]={{20000,0},{0,-20000},{-20000,0},{0,20000},{-17000,-13000}};
    for(unsigned i=0;i<5;i++){
        p=fx_pad_normalize(FX_PAD_LEFT,1,0,raw[i][0],raw[i][1],888,999);
        assert(p.lx==left[i][0]&&p.ly==left[i][1]&&!p.rx&&!p.ry);
        p=fx_pad_normalize(FX_PAD_RIGHT,1,0,888,999,raw[i][0],raw[i][1]);
        assert(p.lx==right[i][0]&&p.ly==right[i][1]&&!p.rx&&!p.ry);
    }
    p=fx_pad_normalize(FX_PAD_LEFT,1,0,INT_MAX,INT_MIN,0,0);assert(p.lx==32767&&p.ly==32767);
    p=fx_pad_normalize(FX_PAD_RIGHT,1,0,0,0,INT_MIN,INT_MAX);assert(p.lx==32767&&p.ly==32767);
    const uint64_t l[]={FX_PAD_DOWN,FX_PAD_LEFT_BUTTON,FX_PAD_UP,FX_PAD_RIGHT_BUTTON};
    const uint64_t r[]={FX_PAD_X,FX_PAD_A,FX_PAD_B,FX_PAD_Y};
    const uint64_t canonical[]={FX_PAD_A,FX_PAD_B,FX_PAD_Y,FX_PAD_X};
    const unsigned xbox[]={XINPUT_GAMEPAD_B,XINPUT_GAMEPAD_A,XINPUT_GAMEPAD_X,XINPUT_GAMEPAD_Y};
    for(unsigned i=0;i<4;i++)for(int kind=FX_PAD_LEFT;kind<=FX_PAD_RIGHT;kind++){
        p=fx_pad_normalize(kind,1,kind==FX_PAD_LEFT?l[i]:r[i],0,0,0,0);
        assert(p.buttons==canonical[i]);XINPUT_GAMEPAD g;
        nx_xinput_map(p.buttons,p.lx,p.ly,p.rx,p.ry,&g);assert(g.wButtons==xbox[i]);
        assert(!(g.wButtons&15)); /* No duplicate D-pad action on the left Joy-Con. */
    }
    for(int kind=FX_PAD_LEFT;kind<=FX_PAD_RIGHT;kind++){
        p=fx_pad_normalize(kind,1,FX_PAD_SL|FX_PAD_SR|FX_PAD_ZL|FX_PAD_ZR|FX_PAD_L|FX_PAD_R|FX_PAD_MINUS|FX_PAD_RSTICK,0,0,0,0);
        assert(p.buttons==(FX_PAD_L|FX_PAD_R|FX_PAD_PLUS|FX_PAD_LSTICK));
        assert(!fx_pad_neutral(&p));
    }
    /* Exhaust every original button chord: full/paired/handheld results unchanged. */
    for(unsigned b=0;b<65536;b++)for(int kind=0;kind<=FX_PAD_HANDHELD;kind++){
        if(kind==FX_PAD_LEFT||kind==FX_PAD_RIGHT)continue;
        XINPUT_GAMEPAD old={0},now={0};p=fx_pad_normalize(kind,1,b,-32768,32767,-9000,9000);
        nx_xinput_map(b,-32768,32767,-9000,9000,&old);
        nx_xinput_map(p.buttons,p.lx,p.ly,p.rx,p.ry,&now);assert(!memcmp(&old,&now,sizeof(old)));
    }
    struct fx_pad_sample slots[2]={{0}};
    fx_pad_update(&slots[0],fx_pad_normalize(FX_PAD_LEFT,1,FX_PAD_DOWN,0,0,0,0));
    fx_pad_update(&slots[1],fx_pad_normalize(FX_PAD_RIGHT,1,FX_PAD_A,0,0,0,0));
    assert(slots[0].packet==1&&slots[1].packet==1&&slots[0].buttons!=slots[1].buttons);
    fx_pad_update(&slots[0],slots[0]);assert(slots[0].packet==1);
    fx_pad_update(&slots[0],fx_pad_normalize(FX_PAD_LEFT,0,~0ull,1,2,3,4));
    assert(slots[0].packet==2&&!slots[0].connected&&!slots[0].buttons&&slots[1].packet==1);
    struct fx_reconnect recovery={FX_RECONNECT_RUNNING,3};
    assert(!fx_reconnect_poll(&recovery,3,1,0));
    assert(fx_reconnect_poll(&recovery,2,0,0));
    for(int i=0;i<100;i++)assert(!fx_reconnect_poll(&recovery,0,1,1));
    assert(recovery.phase==FX_RECONNECT_APPLET); /* Only the owner opens the applet once. */
    recovery.phase=FX_RECONNECT_NEUTRAL; /* cancelled or completed applet */
    fx_reconnect_poll(&recovery,3,0,1);assert(recovery.phase==FX_RECONNECT_NEUTRAL);
    fx_reconnect_poll(&recovery,3,1,0);assert(recovery.phase==FX_RECONNECT_WAIT);
    fx_reconnect_poll(&recovery,1,1,1);assert(recovery.phase==FX_RECONNECT_WAIT);
    fx_reconnect_poll(&recovery,3,1,0);assert(recovery.phase==FX_RECONNECT_WAIT);
    fx_reconnect_poll(&recovery,3,0,1);assert(recovery.phase==FX_RECONNECT_DRAIN);
    fx_reconnect_poll(&recovery,3,0,0);assert(recovery.phase==FX_RECONNECT_DRAIN);
    fx_reconnect_poll(&recovery,1,1,0);assert(recovery.phase==FX_RECONNECT_NEUTRAL);
    fx_reconnect_poll(&recovery,3,1,0);fx_reconnect_poll(&recovery,3,0,1);
    fx_reconnect_poll(&recovery,3,1,0);assert(recovery.phase==FX_RECONNECT_RUNNING);
    recovery.required=1;assert(!fx_reconnect_poll(&recovery,1,1,0));
    assert(fx_reconnect_poll(&recovery,0,1,0));
    p=fx_pad_normalize(FX_PAD_FULL,1,FX_PAD_SL,0,0,0,0);assert(!fx_pad_neutral(&p));
    puts("PASS: Joy-Con axes/buttons, original full-pad XInput chords, independent slots, recovery and button drain");
}
