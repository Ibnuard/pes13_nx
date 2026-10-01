/* LGPL-2.1-or-later. Uses the same normalized samples as XInput. */
#ifdef FX_KEYBOARD_OVERLAY
#include "fextendo_osk_sprites.h"
#endif
static const char *fx_pad_name(int kind) {
    switch(kind){
    case FX_PAD_LEFT:return "Joy-Con (L) / horizontal";
    case FX_PAD_RIGHT:return "Joy-Con (R) / horizontal";
    case FX_PAD_DUAL:return "Joy-Con pair";
    case FX_PAD_HANDHELD:return "Handheld";
    default:return "Full gamepad";
    }
}
static void fx_pad_button(struct fx_canvas *c,int x,int y,const char *label,int on) {
    fx_circle(c,x,y,20,on?FX_BLUE:FX_COLOR(36,56,76));
    fx_center(c,x,y-12,label,0,on?FX_COLOR(7,23,38):FX_WHITE);
}
static void fx_pad_card(struct fx_canvas *c,int x,int index,const struct fx_pad_sample *p,int enabled,int live) {
    struct fx_pad_sample idle=*p;
    if(!live){idle.buttons=0;idle.lx=idle.ly=idle.rx=idle.ry=0;p=&idle;}
    char title[40];uint32_t col=p->connected&&enabled?FX_BLUE:FX_MUTED;
    fx_round(c,x,185,548,335,20,FX_COLOR(12,28,46),255);
    snprintf(title,sizeof(title),"Player %d  /  %s",index+1,!enabled?"Not in session":p->connected?"Connected":"Disconnected");
    fx_text(c,x+26,205,title,1,col);
    fx_text(c,x+26,245,p->connected?fx_pad_name(p->kind):"Connect a controller to this slot",0,FX_MUTED);
    for(int i=0;i<2;i++){
        int cx=x+85+i*120,cy=350;
        fx_circle(c,cx,cy,41,FX_COLOR(28,48,67));
        fx_rect(c,cx-33,cy,67,1,FX_MUTED,90);fx_rect(c,cx,cy-33,1,67,FX_MUTED,90);
        fx_circle(c,cx+(i?p->rx:p->lx)*30/32768,cy-(i?p->ry:p->ly)*30/32768,10,live?col:FX_MUTED);
        fx_center(c,cx,405,i?"Right stick":"Left stick",3,FX_MUTED);
    }
    fx_pad_button(c,x+415,312,"X",!!(p->buttons&FX_PAD_X));
    fx_pad_button(c,x+458,355,"A",!!(p->buttons&FX_PAD_A));
    fx_pad_button(c,x+415,398,"B",!!(p->buttons&FX_PAD_B));
    fx_pad_button(c,x+372,355,"Y",!!(p->buttons&FX_PAD_Y));
    const char *labels[]={"L","R","ZL","ZR","+","-","LS","RS"};
    const uint64_t bits[]={FX_PAD_L,FX_PAD_R,FX_PAD_ZL,FX_PAD_ZR,FX_PAD_PLUS,FX_PAD_MINUS,FX_PAD_LSTICK,FX_PAD_RSTICK};
    for(int i=0;i<8;i++)fx_pad_button(c,x+48+i*64,466,labels[i],!!(p->buttons&bits[i]));
}
static void fx_gamepad_page(struct fx_canvas *c,const struct fx_view *v) {
    fx_rect(c,0,0,FX_W,FX_H,FX_COLOR(5,16,29),255);
    fx_text(c,64,42,"Gamepad",2,FX_WHITE);
    fx_text(c,66,99,v->pad_test?"Live test / Nintendo button labels":"Check connected controllers or start an input test.",0,FX_MUTED);
    fx_pad_card(c,64,0,&v->pads[0],1,v->pad_test);fx_pad_card(c,668,1,&v->pads[1],1,v->pad_test);
    const char *items[]={"Change Controller","Test Controls"};
    for(int i=0;i<2;i++){
        int x=64+i*604;fx_round(c,x,549,548,60,14,v->row==i?FX_COLOR(24,102,143):FX_COLOR(16,36,56),255);
        fx_center(c,x+274,566,items[i],0,FX_WHITE);
    }
    fx_text(c,66,633,v->message?v->message:"Single Joy-Con: SL / SR = L / R. No ZL / ZR. Full pads keep their controls.",0,FX_MUTED);
    if(v->pad_test)fx_text(c,66,681,"+ / -   Finish test",0,FX_WHITE);
    else{fx_hint(c,66,689,"A","Select");fx_hint(c,252,689,"B","Back");}
}
static void fx_gamepad_pause(struct fx_canvas *c,const struct fx_pad_sample pads[2],unsigned players,int ready,int draining,int applet_ok) {
    fx_rect(c,0,0,FX_W,FX_H,FX_COLOR(5,16,29),255);
    fx_text(c,64,42,"Game paused",2,FX_WHITE);
    fx_text(c,66,105,"Controller disconnected. Reconnect it to continue.",0,FX_MUTED);
    fx_pad_card(c,64,0,&pads[0],1,0);fx_pad_card(c,668,1,&pads[1],players==2,0);
#ifdef FX_KEYBOARD_OVERLAY
    if(!draining&&ready){
        fx_image(c,fx_osk_sprites[FX_OSK_SPRITE_A],40,40,66,555,36,36,0,255);
        fx_text(c,110,560,"Continue",1,FX_WHITE);
    }else fx_text(c,66,560,draining?"Release all buttons and sticks.":"Waiting for the session controllers to reconnect...",1,FX_WHITE);
    fx_image(c,fx_osk_sprites[FX_OSK_SPRITE_X],40,40,66,611,36,36,0,255);
    fx_text(c,110,616,"Change Controller",0,FX_BLUE);
#else
    fx_text(c,66,560,draining?"Release all buttons and sticks.":ready?"A   Continue":"Waiting for the session controllers to reconnect...",1,FX_WHITE);
    fx_text(c,66,616,"X   Change Controller",0,FX_BLUE);
#endif
    if(!applet_ok)fx_text(c,66,668,"Controller setup was canceled or failed. Press X to try again.",0,FX_MUTED);
}
