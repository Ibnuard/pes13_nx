/* LGPL-2.1-or-later. Software UI, shared by Switch and host screenshot tests. */
#ifndef FEXTENDO_UI_H
#define FEXTENDO_UI_H
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#include "fextendo_gamepad.h"
#include "fextendo_keyboard_options.h"
#define FX_W 1280
#define FX_H 720
#define FX_COLOR(r,g,b) ((uint32_t)(r)|((uint32_t)(g)<<8)|((uint32_t)(b)<<16)|0xff000000u)
#define FX_WHITE FX_COLOR(242,248,252)
#define FX_MUTED FX_COLOR(170,185,208)
#define FX_BLUE FX_COLOR(51,194,255)
#define FX_APP_VERSION "0.3.8-r6"
#define FX_RELEASE "v3.8-r4"
#define FX_TILE_MIN 212
#define FX_TILE_MAX 260
#define FX_SCENES 6
#ifndef FX_SPLASH_MS
#define FX_SPLASH_MS 2400
#endif
enum fx_screen { FX_HOME,FX_SETTINGS,FX_LOADING,FX_FAILED,FX_CREDITS,FX_GAMEPAD };
struct fx_view { struct fx_pad_sample pads[2]; unsigned players; int pad_test; enum fx_screen screen;int tile,row,selected,saved,fatal,timestamp,sound,battery,charging,credit_page,music,renderer,settings_page,debug_launch;float tile_mix,settings_scroll;unsigned frame,splash_ms;uint64_t last_played,wall_time;const char *message; };
#include "fextendo_settings.h"
struct fx_art { uint32_t *bg,*blur,*logo,*icon,*buttons,*gamepad,*wordmark,*settings_icon,*credits_icon,*gamepad_icon,*scene[FX_SCENES],*tiles[4][FX_TILE_MAX-FX_TILE_MIN+1];uint16_t spinner[43*43];float decay[4097];unsigned char *font;size_t font_size; };
struct fx_canvas { uint32_t *pixels;int stride;const struct fx_art *art;int clip_top,clip_bottom,clip_left,clip_right; };
static int fx_prepare_art(struct fx_art *a);
static void *fx_asset_read(const char *path,size_t expected) {
    void *p=malloc(expected);if(!p)return NULL;
    if(fx_read(path,p,expected)!=expected){free(p);return NULL;}return p;
}
static void fx_art_free(struct fx_art *a) {for(int i=0;i<FX_SCENES;i++)free(a->scene[i]);for(int k=0;k<4;k++)for(int i=0;i<=FX_TILE_MAX-FX_TILE_MIN;i++)free(a->tiles[k][i]);free(a->gamepad_icon);free(a->settings_icon);free(a->credits_icon);free(a->bg);free(a->blur);free(a->logo);free(a->icon);free(a->buttons);free(a->gamepad);free(a->wordmark);free(a->font);memset(a,0,sizeof(*a));}
static int fx_font_load(struct fx_art *a,const char *root) {
    char p[768];struct stat st;unsigned i;
    snprintf(p,sizeof(p),"%s/launcher/font.bin",root);
    if(stat(p,&st)||st.st_size<6088||st.st_size>1024*1024)return 0;
    a->font_size=st.st_size;a->font=fx_asset_read(p,a->font_size);
    if(!a->font||memcmp(a->font,"FXF2",4)||fx_u32(a->font+4)!=a->font_size-6088)return 0;
    for(i=0;i<380;i++){
        const unsigned char *g=a->font+8+i*16;
        unsigned w=g[8]|g[9]<<8,h=g[10]|g[11]<<8;
        if(w>96||h>96||fx_u32(g)>a->font_size-6088||w*h>a->font_size-6088-fx_u32(g))return 0;
    }
    return 1;
}
static int fx_art_load(struct fx_art *a,const char *root) {
    char p[768];memset(a,0,sizeof(*a));
    snprintf(p,sizeof(p),"%s/launcher/background.rgba",root);a->bg=fx_asset_read(p,FX_W*FX_H*4);
    snprintf(p,sizeof(p),"%s/launcher/blur.rgba",root);a->blur=fx_asset_read(p,FX_W*FX_H*4);
    snprintf(p,sizeof(p),"%s/launcher/logo.rgba",root);a->logo=fx_asset_read(p,480*158*4);
    snprintf(p,sizeof(p),"%s/launcher/icon.rgba",root);a->icon=fx_asset_read(p,256*256*4);
    snprintf(p,sizeof(p),"%s/launcher/settings-icon.rgba",root);a->settings_icon=fx_asset_read(p,256*256*4);
    snprintf(p,sizeof(p),"%s/launcher/credits-icon.rgba",root);a->credits_icon=fx_asset_read(p,256*256*4);
    snprintf(p,sizeof(p),"%s/launcher/buttons.rgba",root);a->buttons=fx_asset_read(p,7*80*80*4);
    snprintf(p,sizeof(p),"%s/launcher/gamepad.rgba",root);a->gamepad=fx_asset_read(p,128*96*4);
    snprintf(p,sizeof(p),"%s/launcher/wordmark.rgba",root);a->wordmark=fx_asset_read(p,600*128*4);
    if(!fx_font_load(a,root))goto fail;
    if(a->settings_icon&&a->credits_icon&&a->bg&&a->blur&&a->logo&&a->icon&&a->buttons&&a->gamepad&&a->wordmark&&fx_prepare_art(a))return 1;
fail:fx_art_free(a);return 0;
}
static uint32_t fx_blend(uint32_t dst,uint32_t src,unsigned a) {
    unsigned r=((dst&255)*(255-a)+(src&255)*a+127)/255;
    unsigned g=(((dst>>8)&255)*(255-a)+((src>>8)&255)*a+127)/255;
    unsigned b=(((dst>>16)&255)*(255-a)+((src>>16)&255)*a+127)/255;
    return FX_COLOR(r,g,b);
}
static void fx_rect(struct fx_canvas *c,int x,int y,int w,int h,uint32_t color,unsigned alpha) {
    int right=x+w,bottom=y+h,xx,yy;if(x<0)x=0;if(y<0)y=0;if(right>FX_W)right=FX_W;if(bottom>FX_H)bottom=FX_H;
    if(c->clip_bottom){if(y<c->clip_top)y=c->clip_top;if(bottom>c->clip_bottom)bottom=c->clip_bottom;}
    if(c->clip_right){if(x<c->clip_left)x=c->clip_left;if(right>c->clip_right)right=c->clip_right;}
    for(yy=y;yy<bottom;yy++)for(xx=x;xx<right;xx++){
        uint32_t *p=c->pixels+yy*c->stride+xx;*p=alpha==255?color:fx_blend(*p,color,alpha);}
}
static int fx_text_width(const struct fx_art *a,const char *s,int font) {
    int w=0;for(;*s;s++){unsigned n=(unsigned char)*s;if(n<32||n>126)n='?';
        const unsigned char *g=a->font+8+(font*95+n-32)*16;w+=g[12]|g[13]<<8;}return w;
}
static void fx_text(struct fx_canvas *c,int x,int y,const char *s,int font,uint32_t color) {
    static const int heights[4]={20,26,40,14};
    for(;*s;s++){
        unsigned n=(unsigned char)*s;if(n<32||n>126)n='?';
        const unsigned char *g=c->art->font+8+(font*95+n-32)*16;
        int bx=(int16_t)(g[4]|g[5]<<8),by=(int16_t)(g[6]|g[7]<<8);
        int w=g[8]|g[9]<<8,h=g[10]|g[11]<<8,xx,yy;
        const unsigned char *mask=c->art->font+6088+fx_u32(g);
        for(yy=0;yy<h;yy++)for(xx=0;xx<w;xx++){
            int dx=x+bx+xx,dy=y+heights[font]+by+yy;
            if(dx>=0&&dx<FX_W&&dy>=0&&dy<FX_H&&(!c->clip_right||(dx>=c->clip_left&&dx<c->clip_right))&&(!c->clip_bottom||(dy>=c->clip_top&&dy<c->clip_bottom))&&mask[yy*w+xx]){
                uint32_t *p=c->pixels+dy*c->stride+dx;*p=fx_blend(*p,color,mask[yy*w+xx]);}}
        x+=g[12]|g[13]<<8;
    }
}
static void fx_center(struct fx_canvas *c,int x,int y,const char *s,int font,uint32_t color) {
    fx_text(c,x-fx_text_width(c->art,s,font)/2,y,s,font,color);
}
/* Analytic coverage at the pixel center: all curves have a one-pixel AA fringe. */
static float fx_clamp(float x,float lo,float hi) {return fmaxf(lo,fminf(hi,x));}
static float fx_round_distance(float x,float y,float w,float h,float r) {
    float qx=fabsf(x-w*.5f)-(w*.5f-r),qy=fabsf(y-h*.5f)-(h*.5f-r);
    if(qx<=0||qy<=0)return fmaxf(qx,qy)-r;
    return hypotf(qx,qy)-r;
}
static void fx_put(struct fx_canvas *c,int x,int y,uint32_t color,unsigned a) {
    if(x>=0&&x<FX_W&&y>=0&&y<FX_H&&(!c->clip_right||(x>=c->clip_left&&x<c->clip_right))&&(!c->clip_bottom||(y>=c->clip_top&&y<c->clip_bottom))&&a){uint32_t *d=c->pixels+y*c->stride+x;*d=fx_blend(*d,color,a);}
}
static void fx_circle(struct fx_canvas *c,int x,int y,int r,uint32_t col) {
    for(int yy=-r;yy<=r;yy++)for(int xx=-r;xx<=r;xx++)
        fx_put(c,x+xx,y+yy,col,(unsigned)(255*fx_clamp(r+.5f-hypotf(xx,yy),0,1)));
}
static void fx_round(struct fx_canvas *c,int x,int y,int w,int h,int r,uint32_t col,unsigned a) {
    r=(int)fminf(r,fminf(w,h)*.5f);
    fx_rect(c,x+r,y,w-2*r,h,col,a);
    fx_rect(c,x,y+r,r,h-2*r,col,a);fx_rect(c,x+w-r,y+r,r,h-2*r,col,a);
    for(int yy=0;yy<r;yy++)for(int xx=0;xx<r;xx++){
        float d=hypotf(r-xx-.5f,r-yy-.5f)-r;
        unsigned alpha=(unsigned)(a*fx_clamp(.5f-d,0,1));
        fx_put(c,x+xx,y+yy,col,alpha);fx_put(c,x+w-1-xx,y+yy,col,alpha);
        fx_put(c,x+xx,y+h-1-yy,col,alpha);fx_put(c,x+w-1-xx,y+h-1-yy,col,alpha);
    }
}
/* Premultiplied bilinear sampling avoids both nearest-neighbour steps and
 * dark fringes at the transparent edges of generated artwork. */
static void fx_image(struct fx_canvas *c,const uint32_t *src,int sw,int sh,int x,int y,int w,int h,int r,unsigned opacity) {
    if(w<=0||h<=0)return;
    for(int yy=0;yy<h;yy++){
        int dy=y+yy;if(dy<0||dy>=FX_H)continue;
        float sy=fx_clamp((yy+.5f)*sh/h-.5f,0,sh-1);int y0=(int)sy,y1=y0+1<sh?y0+1:y0;float ty=sy-y0;
        for(int xx=0;xx<w;xx++){
            int dx=x+xx;if(dx<0||dx>=FX_W)continue;
            float cover=r?fx_clamp(.5f-fx_round_distance(xx+.5f,yy+.5f,w,h,r),0,1):1;
            if(!cover)continue;
            float sx=fx_clamp((xx+.5f)*sw/w-.5f,0,sw-1);int x0=(int)sx,x1=x0+1<sw?x0+1:x0;float tx=sx-x0;
            uint32_t p[4]={src[y0*sw+x0],src[y0*sw+x1],src[y1*sw+x0],src[y1*sw+x1]};
            float weight[4]={(1-tx)*(1-ty),tx*(1-ty),(1-tx)*ty,tx*ty},a=0,red=0,g=0,b=0;
            for(int i=0;i<4;i++){float k=(p[i]>>24)*weight[i];a+=k;red+=(p[i]&255)*k;g+=((p[i]>>8)&255)*k;b+=((p[i]>>16)&255)*k;}
            if(a>.01f)fx_put(c,dx,dy,FX_COLOR((unsigned)(red/a+.5f),(unsigned)(g/a+.5f),(unsigned)(b/a+.5f)),(unsigned)(a*opacity/255*cover+.5f));
        }
    }
}
static void fx_sprite(struct fx_canvas *c,int id,int x,int y,int size) {
    fx_image(c,c->art->buttons+id*6400,80,80,x,y,size,size,0,255);
}
/* Keep three roomy rows fully visible at rest, including the focused row. */
static void fx_motion_step(struct fx_view *v,float ms) {
    float target=(float)v->tile;
    v->tile_mix=target+(v->tile_mix-target)*expf(-fx_clamp(ms,0,100)/65.f);
    if(fabsf(v->tile_mix-target)<.001f)v->tile_mix=target;
    target=fx_settings_scroll_target(v->row,v->settings_page);
    v->settings_scroll=target+(v->settings_scroll-target)*expf(-fx_clamp(ms,0,100)/65.f);
    if(fabsf(v->settings_scroll-target)<.1f)v->settings_scroll=target;
}
static void fx_text_middle(struct fx_canvas *c,int x,int center,const char *s,uint32_t color) {
    int top=96,bottom=-96;
    for(const char *p=s;*p;p++){
        unsigned n=(unsigned char)*p;if(n<32||n>126)n='?';
        const unsigned char *g=c->art->font+8+(n-32)*16;
        int by=(int16_t)(g[6]|g[7]<<8),h=g[10]|g[11]<<8;
        if(h){if(by<top)top=by;if(by+h>bottom)bottom=by+h;}
    }
    fx_text(c,x,center-(top+bottom)/2-20,s,0,color);
}
static void fx_hint(struct fx_canvas *c,int x,int center,const char *key,const char *label) {
    int id=*key=='B'?1:*key=='L'?2:*key=='R'?3:*key=='+'?4:*key=='H'?5:*key=='Y'?6:0;
    fx_sprite(c,id,x,center-18,36);fx_text_middle(c,x+42,center,label,FX_WHITE);
}
/* Opaque cover art is scaled once for each animated tile size. */
static void fx_tile_image(struct fx_canvas *c,int x,int y,int w,int id,int dim) {
    const uint32_t *tile=c->art->tiles[id][w-FX_TILE_MIN];
    int left=x<0?-x:0,right=w,top=y<0?-y:0,bottom=w;
    if(x+right>FX_W)right=FX_W-x;if(y+bottom>FX_H)bottom=FX_H-y;
    if(c->clip_right){if(x+left<c->clip_left)left=c->clip_left-x;if(x+right>c->clip_right)right=c->clip_right-x;}
    for(int yy=top;yy<bottom;yy++)for(int xx=left;xx<right;xx++){
        uint32_t p=tile[yy*w+xx];unsigned a=p>>24;
        /* Dim in the same copy pass, without re-evaluating rounded geometry. */
        if(dim)p=fx_blend(p,FX_COLOR(2,8,16),45);
        uint32_t *dst=c->pixels+(y+yy)*c->stride+x+xx;
        if(a==255)*dst=p;
        else if(a)*dst=fx_blend(*dst,p,a);
    }
}
/* One moving light supplies both the glass gradient and its soft edge bloom.
 * Arc-length motion follows the rounded contour without a hard head/tail seam. */
struct fx_light {float x,y;};
static struct fx_light fx_orbit(int w,int h,int r,unsigned frame) {
    const float pi=3.141592654f;float a=w-2*r,b=h-2*r,q=r*pi*.5f;
    float t=(frame%360)/360.f*(2*a+2*b+4*q);struct fx_light l;
    if(t<a){l.x=r+t;l.y=0;return l;}t-=a;
    if(t<q){float z=t/r-pi*.5f;l.x=w-r+r*cosf(z);l.y=r+r*sinf(z);return l;}t-=q;
    if(t<b){l.x=w;l.y=r+t;return l;}t-=b;
    if(t<q){float z=t/r;l.x=w-r+r*cosf(z);l.y=h-r+r*sinf(z);return l;}t-=q;
    if(t<a){l.x=w-r-t;l.y=h;return l;}t-=a;
    if(t<q){float z=t/r+pi*.5f;l.x=r+r*cosf(z);l.y=h-r+r*sinf(z);return l;}t-=q;
    if(t<b){l.x=0;l.y=h-r-t;return l;}t-=b;
    float z=t/r+pi;l.x=r+r*cosf(z);l.y=r+r*sinf(z);return l;
}
static float fx_decay(const struct fx_art *a,float value) {
    unsigned index=(unsigned)(value*256.f);
    return index<4096?a->decay[index]:0.f;
}
static void fx_light_axes(int w,int h,struct fx_light l,float *xs,float *ys,int pad) {
    for(int x=-pad;x<w+pad;x++){float dx=(x+.5f-l.x)/(w*.54f+10);xs[x+pad]=expf(-dx*dx*1.35f);}
    for(int y=-pad;y<h+pad;y++){float dy=(y+.5f-l.y)/(h*.88f+10);ys[y+pad]=expf(-dy*dy*1.35f);}
}
static void fx_glass(struct fx_canvas *c,int x,int y,int w,int h,int r,unsigned frame,int artwork) {
    struct fx_light l=fx_orbit(w,h,r,frame);float xs[FX_W],ys[FX_H];
    fx_light_axes(w,h,l,xs,ys,0);
    for(int yy=0;yy<h;yy++)for(int xx=0;xx<w;xx++){
        float d=fx_round_distance(xx+.5f,yy+.5f,w,h,r),coverage=fx_clamp(.5f-d,0,1);
        if(!coverage)continue;
        float light=xs[xx]*ys[yy];
        if(artwork){
            float rim=fx_decay(c->art,d*d/420.f);
            fx_put(c,x+xx,y+yy,FX_COLOR(44,163,235),(unsigned)(coverage*light*rim*28));
        }else{
            float shade=.18f+.80f*light+.02f*(1-yy/(float)h);
            uint32_t color=fx_blend(FX_COLOR(2,6,12),FX_COLOR(8,112,241),(unsigned)(shade*255));
            /* Light-facing blue is saturated; the dark side shows the stadium. */
            fx_put(c,x+xx,y+yy,color,(unsigned)(coverage*(174+72*light)));
        }
    }
}
static void fx_glow(struct fx_canvas *c,int x,int y,int w,int h,int r,unsigned frame,float intensity) {
    struct fx_light l=fx_orbit(w,h,r,frame);float xs[FX_W+36],ys[FX_H+36];
    fx_light_axes(w,h,l,xs,ys,18);
    int border=r+18;
    for(int yy=-18;yy<h+18;yy++)for(int xx=-18;xx<w+18;xx++){
        /* Only the perimeter contributes; skip the entire interior span. */
        if(yy>=border&&yy<h-border&&xx==border)xx=w-border;
        float signed_d=fx_round_distance(xx+.5f,yy+.5f,w,h,r),d=fabsf(signed_d);if(d>18)continue;
        float light=xs[xx+18]*ys[yy+18];
        float halo=fx_decay(c->art,d*d/(signed_d<0?12.f:66.f))*(8+light*144);
        float edge=fx_decay(c->art,d*d/1.35f)*(4+light*225);
        fx_put(c,x+xx,y+yy,FX_COLOR(5,124,255),(unsigned)fx_clamp(halo*intensity,0,190));
        fx_put(c,x+xx,y+yy,FX_COLOR(24,207,255),(unsigned)fx_clamp(edge*intensity,0,240));
    }
}
static void fx_focus(struct fx_canvas *c,int x,int y,int w,int h,int r,unsigned frame) {
    fx_glow(c,x,y,w,h,r,frame,1.f);
}
static void fx_play(struct fx_canvas *c,int x,int y,int focus,unsigned frame) {
    if(focus){fx_glass(c,x,y,240,58,29,frame,0);fx_glow(c,x,y,240,58,29,frame,1.f);}
    else fx_round(c,x,y,240,58,29,FX_COLOR(9,19,31),218);
    uint32_t ink=focus?FX_WHITE:FX_COLOR(113,132,153);
    int group_x=x+(240-24-12-fx_text_width(c->art,"Play",0))/2;
    /* Rounded AA triangle, sampled above native resolution. */
    for(int yy=0;yy<26;yy++)for(int xx=0;xx<24;xx++){
        unsigned hit=0;
        for(int sy=0;sy<4;sy++)for(int sx=0;sx<4;sx++){
            float px=xx+(sx+.5f)/4,py=yy+(sy+.5f)/4;
            hit+=px>1&&px<22&&fabsf(py-13)<(23-px)*.56f;
        }
        fx_put(c,group_x+xx,y+16+yy,ink,hit*255/16);
    }
    fx_text_middle(c,group_x+36,y+29,"Play",ink);
}
static void fx_frost(struct fx_canvas *c,int top,int bottom,int side) {
    for(int y=top;y<bottom;y++)for(int x=0;x<FX_W;x++){
        float mask=side==0?1.f:side<0?fx_clamp((460.f-x)/130.f,0,1):fx_clamp((x-870.f)/105.f,0,1);
        if(!mask)continue;
        uint32_t frosted=fx_blend(c->art->blur[y*FX_W+x],FX_COLOR(4,10,18),155);
        fx_put(c,x,y,frosted,(unsigned)(mask*235));
    }
}
static void fx_footer(struct fx_canvas *c) {fx_frost(c,658,FX_H,0);}
static void fx_header(struct fx_canvas *c) {
    fx_frost(c,0,78,-1);fx_frost(c,0,78,1);
    fx_image(c,c->art->gamepad,128,96,39,21,44,33,0,255);
    fx_text(c,119,26,"PES13",0,FX_WHITE);
    fx_round(c,117,63,59,3,1,FX_BLUE,230);
    fx_image(c,c->art->icon,256,256,964,17,42,42,11,255);
    fx_image(c,c->art->wordmark,600,128,1018,16,125,27,0,255);
    fx_text(c,1018,45,"by AndroSwitch Project",3,FX_MUTED);
}
static void fx_battery(struct fx_canvas *c,const struct fx_view *v) {
    fx_round(c,1214,23,33,16,4,FX_MUTED,255);
    fx_round(c,1216,25,29,12,2,FX_COLOR(8,17,26),255);
    fx_round(c,1248,28,3,6,1,FX_MUTED,255);
    if(v->battery>=0){
        int fill=(int)(25*fx_clamp(v->battery,0,100)/100);
        if(fill)fx_round(c,1218,27,fill,8,1,v->charging?FX_COLOR(104,229,182):FX_WHITE,255);
        char percent[12];snprintf(percent,sizeof(percent),"%d%%",v->battery);
        fx_center(c,1231,45,percent,3,FX_MUTED);
    }else fx_center(c,1231,45,"--",3,FX_MUTED);
}
static void fx_wrapped(struct fx_canvas *c,int x,int y,const char *message,int width) {
    char line[192]={0};size_t used=0;int rows=0;
    while(*message&&rows<3){
        const char *end=message;while(*end&&*end!=' ')end++;
        size_t word=(size_t)(end-message),extra=word+(used!=0);
        if(used&&(used+extra>=sizeof(line)||fx_text_width(c->art,line,0)+20+(int)word*12>width)){
            fx_text(c,x,y+rows*27,line,0,FX_MUTED);rows++;used=0;
        }
        if(rows==3)break;
        if(used)line[used++]=' ';
        while(word--&&used<sizeof(line)-1)line[used++]=*message++;
        line[used]=0;message=end;while(*message==' ')message++;
    }
    if(used&&rows<3)fx_text(c,x,y+rows*27,line,0,FX_MUTED);
}
static void fx_static_scene(struct fx_canvas *c,int settings) {
    int y;
    for(y=0;y<FX_H;y++)memcpy(c->pixels+y*c->stride,c->art->bg+y*FX_W,FX_W*4);
    /* Soft scrims leave the stadium visible and protect label contrast. */
    for(y=0;y<FX_H;y++){
        unsigned a=y>380?(unsigned)(y-380)*170/340:15;
        fx_rect(c,0,y,FX_W,1,FX_COLOR(3,9,20),a);
    }
    fx_header(c);
    if(!settings){
        fx_image(c,c->art->logo,480,158,62,304,438,144,0,255);
        fx_text(c,76,463,"The beautiful game,",1,FX_WHITE);
        fx_text(c,76,493,"reborn.",1,FX_WHITE);
    }else{
        fx_rect(c,0,78,FX_W,580,FX_COLOR(3,12,27),165);
        fx_text(c,66,116,"Make it",2,FX_WHITE);fx_text(c,66,164,"your game.",2,FX_WHITE);
        fx_text(c,69,232,"Your preferences.",0,FX_MUTED);fx_text(c,69,260,"Organized by category.",0,FX_MUTED);
        fx_image(c,c->art->logo,480,158,63,477,276,91,0,220);
        fx_round(c,380,96,834,529,23,FX_COLOR(9,23,41),244);
    }
    fx_footer(c);
    fx_hint(c,210,689,"B","Back");fx_hint(c,950,689,"+","Exit");fx_hint(c,1084,689,"H","HOME");
}
static void fx_credits_scene(struct fx_canvas *c,int page) {
    for(int y=0;y<FX_H;y++)for(int x=0;x<FX_W;x++)
        c->pixels[y*c->stride+x]=fx_blend(c->art->blur[y*FX_W+x],FX_COLOR(3,12,25),192);
    fx_header(c);fx_footer(c);
    fx_text(c,68,127,"BEHIND THE PROJECT",3,FX_BLUE);
    fx_image(c,c->art->wordmark,600,128,60,185,310,66,0,255);
    fx_text(c,70,278,"AndroSwitch Project",0,FX_WHITE);
    fx_text(c,70,333,"AUTHOR",3,FX_MUTED);
    fx_text(c,70,356,"Ibnuard",1,FX_WHITE);
    fx_text(c,70,420,"VERSION",3,FX_MUTED);
    fx_text(c,70,443,FX_APP_VERSION "  /  FEXTendo " FX_RELEASE,0,FX_WHITE);
    fx_text(c,70,539,"PC football. On your Switch.",0,FX_MUTED);
    fx_round(c,405,107,801,516,24,FX_COLOR(16,35,55),178);
    fx_text(c,442,136,"Credits",2,FX_WHITE);
    fx_round(c,page?574:439,201,page?182:120,36,18,FX_COLOR(26,91,131),165);
    fx_text(c,460,208,"Project",0,page?FX_MUTED:FX_WHITE);
    fx_text(c,593,208,"What's new",0,page?FX_WHITE:FX_MUTED);
    fx_text(c,1100,212,page?"2 / 2":"1 / 2",3,FX_MUTED);
    if(!page){
        fx_text(c,446,266,"FEXTendo / AndroSwitch Project",1,FX_WHITE);
        fx_text(c,446,308,"FEX-Emu port to Switch, Horizon/Wine integration,",0,FX_MUTED);
        fx_text(c,446,335,"native launcher and PES-specific runtime work.",0,FX_MUTED);
        fx_text(c,446,387,"Built with open source",1,FX_WHITE);
        fx_text(c,446,429,"FEX-Emu - upstream CPU translation engine.",0,FX_MUTED);
        fx_text(c,446,456,"Autorun / Wine-NX - runtime base and backports.",0,FX_MUTED);
        fx_text(c,446,483,"Wine, DXVK, Mesa and libnx - platform foundations.",0,FX_MUTED);
        fx_text(c,446,553,"Full attribution and licenses: THIRD_PARTY.md",3,FX_MUTED);
        fx_text(c,446,576,"Unofficial project. Supply your own PES 2013 PC v1.0.",3,FX_MUTED);
    }else{
        const char *title[]={FX_RELEASE "  /  Faster API calls","v3.3  /  Renderer choices","v3.1  /  Console navigation"};
        const char *a[]={"Shorter clock and delay paths; same game timing.","DXVK 3.1.1 or 2.7.1 async, saved in Settings.","Focus-only glow, menu audio and on-screen timestamp."};
        const char *b[]={"Shared yield timing and per-thread statistics.","Smaller JIT blocks for the cold-start trial.","Rounded artwork, battery and Last played."};
        for(int i=0;i<3;i++){
            int y=266+i*106;
            fx_text(c,446,y,title[i],1,FX_WHITE);
            fx_text(c,446,y+38,a[i],0,FX_MUTED);
            fx_text(c,446,y+65,b[i],0,FX_MUTED);
        }
    }
    fx_hint(c,56,689,"L","Previous");fx_hint(c,255,689,"R","Next");
    fx_hint(c,427,689,"B","Back");fx_hint(c,950,689,"+","Exit");fx_hint(c,1084,689,"H","HOME");
}
static int fx_prepare_art(struct fx_art *a) {
    for(int i=0;i<=4096;i++)a->decay[i]=expf(-i/256.f);
    for(int y=-21;y<=21;y++)for(int x=-21;x<=21;x++){
        float distance=hypotf(x,y),angle=atan2f(y,x)+1.57079632679f;
        if(angle<0)angle+=6.28318530718f;
        unsigned coverage=(unsigned)(255*fx_clamp(1.8f-fabsf(distance-18),0,1));
        unsigned phase=(unsigned)(angle*256.f/6.28318530718f)&255;
        a->spinner[(y+21)*43+x+21]=(uint16_t)((coverage<<8)|phase);
    }
    a->gamepad_icon=calloc(256*256,4);if(!a->gamepad_icon)return 0;
    /* Restrict the canvas so drawing helpers cannot escape the 256px icon. */
    struct fx_canvas icon_canvas={a->gamepad_icon,256,a,0,256,0,256};
    fx_rect(&icon_canvas,0,0,256,256,FX_COLOR(15,42,62),255);
    fx_image(&icon_canvas,a->gamepad,128,96,24,48,208,156,0,255);
    /* Bilinear RGB for opaque cover art; rounded coverage remains an AA mask. */
    for(int id=0;id<4;id++)for(int w=FX_TILE_MIN;w<=FX_TILE_MAX;w++){
        const uint32_t *icon=id==0?a->icon:id==1?a->settings_icon:id==2?a->gamepad_icon:a->credits_icon;
        uint32_t *tile=a->tiles[id][w-FX_TILE_MIN]=malloc((size_t)w*w*4);if(!tile)return 0;
        for(int y=0;y<w;y++)for(int x=0;x<w;x++){
            float sx=fx_clamp((x+.5f)*256/w-.5f,0,255),sy=fx_clamp((y+.5f)*256/w-.5f,0,255);
            int x0=(int)sx,y0=(int)sy,x1=x0<255?x0+1:x0,y1=y0<255?y0+1:y0;
            unsigned tx=(unsigned)((sx-x0)*256),ty=(unsigned)((sy-y0)*256);
            uint32_t top=fx_blend(icon[y0*256+x0],icon[y0*256+x1],tx>255?255:tx);
            uint32_t bot=fx_blend(icon[y1*256+x0],icon[y1*256+x1],tx>255?255:tx);
            uint32_t rgb=fx_blend(top,bot,ty>255?255:ty);
            unsigned alpha=(unsigned)(255*fx_clamp(.5f-fx_round_distance(x+.5f,y+.5f,w,w,22),0,1));
            tile[y*w+x]=(rgb&0xffffff)|(alpha<<24);
        }
    }
    for(int i=0;i<FX_SCENES;i++){
        a->scene[i]=malloc(FX_W*FX_H*4);if(!a->scene[i])return 0;
        struct fx_canvas c={a->scene[i],FX_W,a,0,0};
        if(i<2)fx_static_scene(&c,i);
        else if(i==2){
            /* Translucent glass is composed once; only the spinner moves. */
            for(int y=0;y<FX_H;y++)for(int x=0;x<FX_W;x++)
                c.pixels[y*FX_W+x]=fx_blend(a->blur[y*FX_W+x],FX_COLOR(2,8,19),135);
            const int left=416,top=154,width=448,height=412,radius=30;
            for(int y=-28;y<height+28;y++)for(int x=-28;x<width+28;x++){
                float d=fx_round_distance(x+.5f,y+.5f,width,height,radius);
                /* A narrow contact shade, no broad black drop shadow. */
                if(d>0)fx_put(&c,left+x,top+y,FX_COLOR(2,8,19),(unsigned)(fx_decay(a,d*d/12.f)*18));
                if(d<=1){
                    float dx=(x-45)/260.f,dy=(y-25)/175.f;
                    float highlight=fx_decay(a,dx*dx+dy*dy);
                    float edge=fx_decay(a,d*d/1.1f);
                    uint32_t tint=fx_blend(FX_COLOR(6,14,29),FX_COLOR(21,69,108),(unsigned)(highlight*210));
                    float cover=fx_clamp(.5f-d,0,1);
                    fx_put(&c,left+x,top+y,tint,(unsigned)(cover*(138+highlight*35)));
                    fx_put(&c,left+x,top+y,FX_COLOR(78,159,210),(unsigned)(cover*edge*(10+highlight*105)));
                }
            }
            /* Light transmitted through the glass behind the cover, baked once. */
            for(int y=-112;y<=112;y++)for(int x=-132;x<=132;x++){
                float dx=x/85.f,dy=y/73.f;
                fx_put(&c,640+x,330+y,FX_COLOR(5,109,233),(unsigned)(fx_decay(a,dx*dx+dy*dy)*53));
            }
            fx_center(&c,640,190,"Launching game",1,FX_WHITE);
            fx_round(&c,570,252,140,140,27,FX_COLOR(96,188,230),105);
            fx_image(&c,a->icon,256,256,573,255,134,134,24,255);
        }else if(i==3){
            for(int y=0;y<FX_H;y++)for(int x=0;x<FX_W;x++){
                float dx=(x-640)/320.f,dy=(y-350)/190.f;
                unsigned amount=(unsigned)(fx_decay(a,dx*dx+dy*dy)*145);
                c.pixels[y*FX_W+x]=fx_blend(FX_COLOR(3,8,17),FX_COLOR(7,39,76),amount);
            }
        }else{
            fx_credits_scene(&c,i-4);
        }
    }
    return 1;
}
static void fx_spinner(struct fx_canvas *c,int x,int y,unsigned frame) {
    unsigned phase=(frame%40)*256/40;
    for(int yy=-21;yy<=21;yy++)for(int xx=-21;xx<=21;xx++){
        unsigned mask=c->art->spinner[(yy+21)*43+xx+21],alpha=mask>>8;if(!alpha)continue;
        unsigned trail=((mask&255)+256-phase)&255;
        uint32_t color=fx_blend(FX_COLOR(32,58,86),FX_BLUE,trail<160?(160-trail)*255/160:0);
        fx_put(c,x+xx,y+yy,color,alpha);
    }
}
static float fx_ease(float t) {t=fx_clamp(t,0,1);return t*t*(3-2*t);}
static void fx_splash(struct fx_canvas *c,unsigned remaining) {
    float elapsed=FX_SPLASH_MS>remaining?FX_SPLASH_MS-remaining:0;
    float reveal=fx_ease(elapsed/680.f),fade=fx_ease(remaining/300.f);
    int lift=(int)lroundf(18*(1-reveal));
    float beam=(elapsed-800)/2.1f;
    /* Native-resolution logo: only alpha/color arithmetic in the frame loop. */
    for(int y=0;y<128;y++)for(int x=0;x<600;x++){
        uint32_t pixel=c->art->wordmark[y*600+x];unsigned alpha=(unsigned)((pixel>>24)*reveal*fade);
        if(!alpha)continue;
        float light=fx_clamp(1-fabsf(x-beam)/66.f,0,1);
        uint32_t tint=fx_blend(pixel,FX_COLOR(156,225,255),(unsigned)(light*55));
        fx_put(c,340+x,262+lift+y,tint,alpha);
    }
    float subtitle=fx_ease((elapsed-420)/600.f)*fade;
    if(subtitle>.01f)fx_center(c,640,413,"by AndroSwitch Project",0,fx_blend(FX_COLOR(5,21,43),FX_MUTED,(unsigned)(subtitle*255)));
    int width=(int)(100*fx_ease((elapsed-550)/950.f));
    if(width)fx_round(c,640-width/2,460,width,2,1,FX_BLUE,(unsigned)(170*fade));
}
#include "fextendo_gamepad_ui.h"
static void fx_render(struct fx_canvas *c,const struct fx_view *v) {
    int y,i;char status[96];
    int scene_index=v->splash_ms?3:v->screen==FX_LOADING?2:v->screen==FX_CREDITS?4+(v->credit_page!=0):v->screen==FX_SETTINGS;
    const uint32_t *scene=c->art->scene[scene_index];
    for(y=0;y<FX_H;y++)memcpy(c->pixels+y*c->stride,scene+y*FX_W,FX_W*4);
    if(v->splash_ms){fx_splash(c,v->splash_ms);return;}
    if(v->screen==FX_LOADING){fx_spinner(c,640,462,v->frame);return;}
    fx_battery(c,v);
    if(v->screen==FX_CREDITS)return;
    if(v->screen==FX_GAMEPAD){fx_gamepad_page(c,v);return;}
    if(v->screen!=FX_SETTINGS){
        fx_play(c,76,552,v->tile==0,v->frame);
        char played[48];fx_last_played_label(played,v->last_played,v->wall_time);
        fx_text(c,76,623,"Last played",0,FX_MUTED);
        fx_text(c,76+fx_text_width(c->art,"Last played",0)+15,623,played,0,FX_WHITE);
        c->clip_left=600;c->clip_right=FX_W;
        int tiles=v->debug_launch?5:4;
        float slide=fx_clamp(v->tile_mix-1,0,tiles-2);
        for(i=0;i<tiles;i++){
            float amount=fx_clamp(1-fabsf(v->tile_mix-i),0,1);
            int w=(int)lroundf(FX_TILE_MIN+(FX_TILE_MAX-FX_TILE_MIN)*amount),x=750+260*i-(int)lroundf(260*slide)-w/2,yy=384-w/2;
            int selected=v->tile==i;
            if(i==4){
                fx_round(c,x,yy,w,w,22,FX_COLOR(8,16,24),255);
                fx_text(c,x+36,yy+w/2-25,">_",2,selected?FX_BLUE:FX_MUTED);
            }else fx_tile_image(c,x,yy,w,i,!selected);
            if(selected)fx_glass(c,x,yy,w,w,22,v->frame,1);
            if(selected)fx_glow(c,x,yy,w,w,22,v->frame,1.f);
            fx_text(c,x+9,yy+w+16,i==4?"Debug launch":i==3?"Credits":i==2?"Gamepad":i?"Settings":"PES13",1,selected?FX_WHITE:FX_MUTED);
            fx_circle(c,x+14,yy+w+65,4,selected?FX_BLUE:FX_COLOR(90,112,140));
            fx_text(c,x+28,yy+w+53,i==4?"Startup console":i==3?"About":i==2?"Controllers":i?"Preferences":"Launch",0,selected?FX_BLUE:FX_MUTED);
        }
        c->clip_left=c->clip_right=0;
        /* Fade the cropped tile back into the cached background, including
         * its label and halo. No extra full-screen offscreen render. */
        for(int x=600;x<FX_W;x++){
            float left=fx_clamp((732-x)/132.f,0,1)*fx_clamp(slide,0,1);
            float right=fx_clamp((x-1160)/120.f,0,1)*fx_clamp(tiles-2-slide,0,1);
            unsigned alpha=(unsigned)(255*fmaxf(left,right));
            if(alpha)for(y=230;y<604;y++){
                uint32_t *p=c->pixels+y*c->stride+x;*p=fx_blend(*p,scene[y*FX_W+x],alpha);
            }
        }
        snprintf(status,sizeof(status),"%s  /  16:9  /  VSync ON",fx_preset_names[v->selected]);
        fx_text(c,643,623,status,0,FX_MUTED);
    }else{
        int rows=fx_settings_rows(v->settings_page);
        fx_text(c,417,122,fx_settings_title(v->settings_page),2,FX_WHITE);
        fx_text(c,417,172,fx_settings_subtitle(v->settings_page),0,FX_MUTED);
        char position[16];snprintf(position,sizeof(position),"%d / %d",v->row+1,rows);
        fx_text(c,1116,135,position,0,FX_MUTED);
        /* Clip every primitive, including text/glow, inside the scroll viewport. */
        c->clip_top=204;c->clip_bottom=560;
        for(i=0;i<rows;i++){
            int on=v->row==i;y=216+i*116-(int)lroundf(v->settings_scroll);
            if(y+118<c->clip_top||y-18>=c->clip_bottom)continue;
            if(on)fx_glass(c,412,y,766,100,14,v->frame,0);
            else fx_round(c,412,y,766,100,14,FX_COLOR(12,25,39),255);
            if(on)fx_focus(c,412,y,766,100,14,v->frame);
            fx_text(c,435,y+20,fx_settings_label(v,i),1,FX_WHITE);
            fx_text(c,437,y+61,fx_settings_detail(v,i),0,FX_MUTED);
            int toggle=fx_settings_toggle(v,i);
            if(fx_settings_selected(v,i)){
                fx_round(c,1060,y+35,95,29,14,FX_COLOR(18,98,132),255);
                fx_center(c,1107,y+38,"SELECTED",3,FX_WHITE);
            }else if(toggle>=0){
                fx_round(c,1080,y+34,72,32,16,toggle?FX_COLOR(21,144,208):FX_COLOR(50,61,76),255);
                fx_circle(c,toggle?1136:1096,y+50,12,FX_WHITE);
            }else if(fx_settings_group(v,i))fx_text(c,1135,y+34,">",1,FX_MUTED);
        }
        for(int fade=0;fade<16;fade++){
            unsigned alpha=(unsigned)(255*(1-fade/16.f)*(1-fade/16.f));
            fx_rect(c,394,204+fade,791,1,FX_COLOR(9,23,41),alpha);
            fx_rect(c,394,559-fade,791,1,FX_COLOR(9,23,41),alpha);
        }
        c->clip_top=c->clip_bottom=0;
        if(rows>3){
            fx_round(c,1194,216,3,332,1,FX_COLOR(32,51,70),255);
            int thumb=(int)(332.f*332.f/(rows*116.f-16.f));
            int thumb_y=216+(int)((332-thumb)*v->settings_scroll/((rows-3)*116.f));
            fx_round(c,1194,thumb_y,3,thumb,1,FX_COLOR(45,142,202),255);
        }
        fx_text(c,418,589,v->saved?"Settings saved. Ready to play.":"16:9 widescreen  /  VSync ON",0,v->saved?FX_BLUE:FX_MUTED);
    }
    fx_hint(c,56,689,"A",v->screen==FX_SETTINGS?(fx_settings_group(v,v->row)?"Open":fx_settings_toggle(v,v->row)>=0?"Toggle":"Apply"):"Select");
    if(v->screen==FX_FAILED){
        int failed=v->screen==FX_FAILED;uint32_t accent=failed?FX_COLOR(255,142,138):FX_BLUE;
        fx_rect(c,0,0,FX_W,FX_H,FX_COLOR(1,7,17),202);
        for(i=12;i>=4;i-=4)fx_round(c,332-i,214+i,616+i*2,294,26+i,FX_COLOR(0,0,0),30);
        fx_round(c,331,207,618,298,25,FX_COLOR(66,93,126),190);
        fx_round(c,333,209,614,294,23,FX_COLOR(14,29,49),255);
        fx_round(c,369,244,50,50,14,failed?FX_COLOR(66,37,49):FX_COLOR(15,62,98),255);
        fx_center(c,394,248,failed?"!":"P",1,accent);
        fx_text(c,438,239,failed?"Launch failed":"Starting PES13",2,FX_WHITE);
        fx_wrapped(c,373,315,v->message?v->message:"Getting your game ready...",532);
        if(!failed){
            fx_round(c,373,418,534,5,2,FX_COLOR(36,58,84),255);
            int pos=v->frame%160;pos=pos<80?pos:160-pos;
            fx_round(c,373+pos*5,418,134,5,2,FX_BLUE,255);
            fx_text(c,373,447,"Your match is loading",0,FX_MUTED);
        }else{
            fx_round(c,371,418,536,52,14,FX_COLOR(28,71,118),255);
            fx_hint(c,498,444,"A",v->fatal?"Close launcher":"Back to launcher");
        }
    }
}
#endif
