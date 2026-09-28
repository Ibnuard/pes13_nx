/* LGPL-2.1-or-later. Software UI, shared by Switch and host screenshot tests. */
#ifndef FEXTENDO_UI_H
#define FEXTENDO_UI_H
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#define FX_W 1280
#define FX_H 720
#define FX_COLOR(r,g,b) ((uint32_t)(r)|((uint32_t)(g)<<8)|((uint32_t)(b)<<16)|0xff000000u)
#define FX_WHITE FX_COLOR(242,248,252)
#define FX_MUTED FX_COLOR(170,185,208)
#define FX_BLUE FX_COLOR(51,194,255)
enum fx_screen { FX_HOME,FX_SETTINGS,FX_LOADING,FX_FAILED };
struct fx_view { enum fx_screen screen;int tile,row,selected,saved,fatal,timestamp;unsigned frame;const char *message; };
struct fx_art { uint32_t *bg,*logo,*icon,*buttons,*gamepad,*wordmark;unsigned char *font;size_t font_size; };
struct fx_canvas { uint32_t *pixels;int stride;const struct fx_art *art; };
static void *fx_asset_read(const char *path,size_t expected) {
    void *p=malloc(expected);if(!p)return NULL;
    if(fx_read(path,p,expected)!=expected){free(p);return NULL;}return p;
}
static void fx_art_free(struct fx_art *a) {free(a->bg);free(a->logo);free(a->icon);free(a->buttons);free(a->gamepad);free(a->wordmark);free(a->font);memset(a,0,sizeof(*a));}
static int fx_art_load(struct fx_art *a,const char *root) {
    char p[768];struct stat st;unsigned i;memset(a,0,sizeof(*a));
    snprintf(p,sizeof(p),"%s/launcher/background.rgba",root);a->bg=fx_asset_read(p,FX_W*FX_H*4);
    snprintf(p,sizeof(p),"%s/launcher/logo.rgba",root);a->logo=fx_asset_read(p,480*158*4);
    snprintf(p,sizeof(p),"%s/launcher/icon.rgba",root);a->icon=fx_asset_read(p,238*238*4);
    snprintf(p,sizeof(p),"%s/launcher/buttons.rgba",root);a->buttons=fx_asset_read(p,7*40*40*4);
    snprintf(p,sizeof(p),"%s/launcher/gamepad.rgba",root);a->gamepad=fx_asset_read(p,64*48*4);
    snprintf(p,sizeof(p),"%s/launcher/wordmark.rgba",root);a->wordmark=fx_asset_read(p,300*64*4);
    snprintf(p,sizeof(p),"%s/launcher/font.bin",root);
    if(stat(p,&st)||st.st_size<4568||st.st_size>1024*1024)goto fail;
    a->font_size=st.st_size;a->font=fx_asset_read(p,a->font_size);
    if(!a->font||memcmp(a->font,"FXF1",4)||fx_u32(a->font+4)!=a->font_size-4568)goto fail;
    for(i=0;i<285;i++){
        const unsigned char *g=a->font+8+i*16;
        unsigned w=g[8]|g[9]<<8,h=g[10]|g[11]<<8;
        if(w>96||h>96||fx_u32(g)>a->font_size-4568||w*h>a->font_size-4568-fx_u32(g))goto fail;
    }
    if(a->bg&&a->logo&&a->icon&&a->buttons&&a->gamepad&&a->wordmark)return 1;
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
    for(yy=y;yy<bottom;yy++)for(xx=x;xx<right;xx++){
        uint32_t *p=c->pixels+yy*c->stride+xx;*p=alpha==255?color:fx_blend(*p,color,alpha);}
}
static int fx_text_width(const struct fx_art *a,const char *s,int font) {
    int w=0;for(;*s;s++){unsigned n=(unsigned char)*s;if(n<32||n>126)n='?';
        const unsigned char *g=a->font+8+(font*95+n-32)*16;w+=g[12]|g[13]<<8;}return w;
}
static void fx_text(struct fx_canvas *c,int x,int y,const char *s,int font,uint32_t color) {
    static const int heights[3]={20,26,40};
    for(;*s;s++){
        unsigned n=(unsigned char)*s;if(n<32||n>126)n='?';
        const unsigned char *g=c->art->font+8+(font*95+n-32)*16;
        int bx=(int16_t)(g[4]|g[5]<<8),by=(int16_t)(g[6]|g[7]<<8);
        int w=g[8]|g[9]<<8,h=g[10]|g[11]<<8,xx,yy;
        const unsigned char *mask=c->art->font+4568+fx_u32(g);
        for(yy=0;yy<h;yy++)for(xx=0;xx<w;xx++){
            int dx=x+bx+xx,dy=y+heights[font]+by+yy;
            if(dx>=0&&dx<FX_W&&dy>=0&&dy<FX_H&&mask[yy*w+xx]){
                uint32_t *p=c->pixels+dy*c->stride+dx;*p=fx_blend(*p,color,mask[yy*w+xx]);}}
        x+=g[12]|g[13]<<8;
    }
}
static void fx_center(struct fx_canvas *c,int x,int y,const char *s,int font,uint32_t color) {
    fx_text(c,x-fx_text_width(c->art,s,font)/2,y,s,font,color);
}
static void fx_circle(struct fx_canvas *c,int x,int y,int r,uint32_t col) {
    int yy;for(yy=-r;yy<=r;yy++){int dx=(int)sqrt((double)(r*r-yy*yy));fx_rect(c,x-dx,y+yy,dx*2+1,1,col,255);}
}
/* Rounded scanlines keep all writes clipped through fx_rect/fx_image. */
static int fx_inset(int row,int h,int radius) {
    int dy=row<radius?radius-row-1:row>=h-radius?row-(h-radius):0;
    return dy?(int)ceil(radius-sqrt((double)radius*radius-(double)dy*dy)):0;
}
static void fx_round(struct fx_canvas *c,int x,int y,int w,int h,int r,uint32_t col,unsigned a) {
    if(r>h/2)r=h/2;
    if(r>w/2)r=w/2;
    for(int yy=0;yy<h;yy++){int n=fx_inset(yy,h,r);fx_rect(c,x+n,y+yy,w-2*n,1,col,a);}
}
static void fx_image(struct fx_canvas *c,const uint32_t *src,int sw,int sh,int x,int y,int w,int h,int r,unsigned opacity) {
    for(int yy=0;yy<h;yy++){
        int n=fx_inset(yy,h,r),dy=y+yy;if(dy<0||dy>=FX_H)continue;
        for(int xx=n;xx<w-n;xx++){
            int dx=x+xx;if(dx<0||dx>=FX_W)continue;
            uint32_t s=src[(yy*sh/h)*sw+xx*sw/w],*d=c->pixels+dy*c->stride+dx;
            *d=fx_blend(*d,s,(s>>24)*opacity/255);
        }
    }
}
static void fx_sprite(struct fx_canvas *c,int id,int x,int y,int size) {
    fx_image(c,c->art->buttons+id*1600,40,40,x,y,size,size,0,255);
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
static void fx_gear(struct fx_canvas *c,int x,int y,int r,uint32_t col) {
    double axes[8][2];
    for(int i=0;i<8;i++){double t=i*3.141592653589793/4;axes[i][0]=cos(t);axes[i][1]=sin(t);}
    for(int yy=-r;yy<=r;yy++)for(int xx=-r;xx<=r;xx++){
        double d=(double)xx*xx+(double)yy*yy;int filled=d<r*r*0.64;
        if(d<r*r*0.13||d>r*r)continue;
        for(int i=0;!filled&&i<8;i++){
            double along=xx*axes[i][0]+yy*axes[i][1],across=yy*axes[i][0]-xx*axes[i][1];
            filled=along>0&&along<r&&fabs(across)<r*0.19;
        }
        if(filled)fx_rect(c,x+xx,y+yy,1,1,col,255);
    }
}
static void fx_focus(struct fx_canvas *c,int x,int y,int w,int h,int r,unsigned frame) {
    unsigned pulse=frame%90<45?frame%45:90-frame%90;
    /* Diffuse light, never a solid stroke around the selected object. */
    for(int g=12;g>=4;g-=4)fx_round(c,x-g,y-g,w+g*2,h+g*2,r+g,FX_BLUE,5+pulse/12);
}
static void fx_gloss(struct fx_canvas *c,int x,int y,int w,int h,int r,unsigned frame) {
    for(int yy=0;yy<h;yy++){
        int n=fx_inset(yy,h,r);
        unsigned top=yy<h/3?(unsigned)(h/3-yy)*48/(h/3):0;
        for(int xx=n;xx<w-n;xx++){
            int d=abs(xx+yy/2-((int)(frame%210)*(w+150)/210-75));
            unsigned a=top+(d<55?(unsigned)(55-d)*18/55:0);
            if(a)fx_rect(c,x+xx,y+yy,1,1,FX_WHITE,a);
        }
    }
}
static void fx_play(struct fx_canvas *c,int x,int y,int focus,unsigned frame) {
    if(focus)fx_focus(c,x,y,223,54,27,frame);
    for(int yy=0;yy<54;yy++){
        int n=fx_inset(yy,54,27);
        uint32_t base=FX_COLOR(9,91+(53-yy),181+(53-yy));
        unsigned gloss=yy<27?(27-yy)*3:0;
        for(int xx=n;xx<223-n;xx++){
            uint32_t col=fx_blend(base,FX_COLOR(158,221,255),gloss);
            /* A soft diagonal reflection traverses the focused glass button. */
            int distance=abs(xx+(yy*2/3)-((int)(frame%150)*4-75));
            if(focus&&distance<42)col=fx_blend(col,FX_WHITE,(42-distance)*2);
            fx_rect(c,x+xx,y+yy,1,1,col,255);
        }
    }
    for(int xx=0;xx<17;xx++)fx_rect(c,x+67+xx,y+16+xx/2,1,23-xx,FX_WHITE,255);
    fx_text(c,x+101,y+11,"Play",1,FX_WHITE);
}
static void fx_footer(struct fx_canvas *c) {
    /* Blur the stadium backdrop before drawing hints. Two small scanline
     * passes avoid retaining a second full-size framebuffer. */
    enum { SCALE=4, W=FX_W/SCALE, H=24, TOP=624, R=4 };
    uint32_t reduced[H][W],horizontal[H][W];
    for(int y=0;y<H;y++)for(int x=0;x<W;x++){
        unsigned r=0,g=0,b=0;
        for(int dy=0;dy<SCALE;dy++)for(int dx=0;dx<SCALE;dx++){
            uint32_t p=c->art->bg[(TOP+y*SCALE+dy)*FX_W+x*SCALE+dx];
            r+=p&255;g+=(p>>8)&255;b+=(p>>16)&255;
        }
        reduced[y][x]=FX_COLOR(r/16,g/16,b/16);
    }
    for(int y=0;y<H;y++)for(int x=0;x<W;x++){
        unsigned r=0,g=0,b=0;
        for(int d=-R;d<=R;d++){
            int sx=x+d;if(sx<0)sx=0;if(sx>=W)sx=W-1;
            uint32_t p=reduced[y][sx];r+=p&255;g+=(p>>8)&255;b+=(p>>16)&255;
        }
        horizontal[y][x]=FX_COLOR(r/(R*2+1),g/(R*2+1),b/(R*2+1));
    }
    for(int y=658;y<FX_H;y++)for(int x=0;x<W;x++){
        unsigned r=0,g=0,b=0;
        for(int d=-R;d<=R;d++){
            int sy=(y-TOP)/SCALE+d;if(sy<0)sy=0;if(sy>=H)sy=H-1;
            uint32_t p=horizontal[sy][x];r+=p&255;g+=(p>>8)&255;b+=(p>>16)&255;
        }
        uint32_t p=fx_blend(FX_COLOR(r/(R*2+1),g/(R*2+1),b/(R*2+1)),FX_COLOR(8,17,31),104);
        fx_rect(c,x*SCALE,y,SCALE,1,p,255);
    }
    fx_rect(c,0,658,FX_W,1,FX_COLOR(174,210,238),60);
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
static void fx_render(struct fx_canvas *c,const struct fx_view *v) {
    int y,i;char status[96];
    for(y=0;y<FX_H;y++)memcpy(c->pixels+y*c->stride,c->art->bg+y*FX_W,FX_W*4);
    /* Soft scrims leave the stadium visible and protect label contrast. */
    for(y=0;y<FX_H;y++){
        unsigned a=y>380?(unsigned)(y-380)*170/340:15;
        fx_rect(c,0,y,FX_W,1,FX_COLOR(3,9,20),a);
    }
    fx_rect(c,0,0,FX_W,65,FX_COLOR(5,12,25),230);
    fx_rect(c,0,64,FX_W,1,FX_COLOR(149,191,232),30);
    fx_image(c,c->art->gamepad,64,48,40,18,40,30,0,255);
    fx_text(c,119,23,"PES13",0,FX_WHITE);
    fx_round(c,119,58,fx_text_width(c->art,"PES13",0),3,1,FX_BLUE,255);
    fx_round(c,934,12,42,42,10,FX_COLOR(15,34,54),255);
    fx_image(c,c->art->icon,238,238,934,12,42,42,10,255);
    fx_image(c,c->art->wordmark,300,64,990,9,144,31,0,255);
    fx_text(c,990,35,"by AndroSwitch Project",0,FX_MUTED);
    if(v->screen!=FX_SETTINGS){
        fx_image(c,c->art->logo,480,158,62,304,438,144,0,255);
        fx_text(c,76,463,"The beautiful game,",1,FX_WHITE);
        fx_text(c,76,493,"reborn.",1,FX_WHITE);
        fx_play(c,76,552,v->tile==0,v->frame);
        for(i=0;i<2;i++){
            int x=i?991:703;
            int yy=i?274:252,w=i?212:260;
            int selected=v->tile==i;
            fx_round(c,x+5,yy+9,w,w,18,FX_COLOR(0,0,0),140);
            if(selected)fx_focus(c,x,yy,w,w,18,v->frame);
            fx_image(c,c->art->icon,238,238,x,yy,w,w,18,255);
            if(i){
                fx_round(c,x,yy,w,w,18,FX_COLOR(5,25,48),218);
                for(int j=0;j<5;j++)fx_round(c,x+25+j*9,yy+26+j*24,w-50,1,0,FX_BLUE,35);
                fx_gear(c,x+w/2,yy+w/2,34,selected?FX_WHITE:FX_MUTED);
            }else if(!selected)fx_round(c,x,yy,w,w,18,FX_COLOR(3,13,28),65);
            if(selected)fx_gloss(c,x,yy,w,w,18,v->frame);
            fx_text(c,x+9,yy+w+16,i?"Settings":"PES13",1,selected?FX_WHITE:FX_MUTED);
            fx_circle(c,x+14,yy+w+65,4,selected?FX_BLUE:FX_COLOR(90,112,140));
            fx_text(c,x+28,yy+w+53,i?"Graphics presets":"Launch",0,selected?FX_BLUE:FX_MUTED);
        }
        snprintf(status,sizeof(status),"%s  /  16:9  /  VSync ON",fx_preset_names[v->selected]);
        fx_text(c,711,623,status,0,FX_MUTED);
    }else{
        fx_rect(c,0,65,FX_W,593,FX_COLOR(3,12,27),165);
        fx_text(c,66,116,"Make it",2,FX_WHITE);fx_text(c,66,164,"your game.",2,FX_WHITE);
        fx_text(c,69,232,"Four presets.",0,FX_MUTED);fx_text(c,69,260,"One press to switch.",0,FX_MUTED);
        fx_image(c,c->art->logo,480,158,63,477,276,91,0,220);
        fx_round(c,380,96,834,529,23,FX_COLOR(9,23,41),244);
        fx_text(c,414,116,"Graphics presets",2,FX_WHITE);
        fx_text(c,417,172,"Choose your balance of detail and performance.",0,FX_MUTED);
        for(i=0;i<4;i++){
            int on=v->row==i;y=211+i*70;
            if(on)fx_focus(c,412,y,770,61,12,v->frame);
            fx_round(c,412,y,770,61,12,on?FX_COLOR(22,58,94):FX_COLOR(18,34,54),255);
            if(on)fx_gloss(c,412,y,770,61,12,v->frame);
            fx_text(c,435,y+3,fx_preset_names[i],1,FX_WHITE);
            fx_text(c,437,y+33,fx_preset_details[i],0,FX_MUTED);
            if(v->selected==i){
                fx_round(c,1060,y+16,95,29,14,FX_COLOR(18,98,132),255);
                fx_center(c,1107,y+19,"ACTIVE",0,FX_WHITE);
            }
        }
        if(v->row==4)fx_focus(c,412,504,770,65,12,v->frame);
        fx_round(c,412,504,770,65,12,v->row==4?FX_COLOR(22,58,94):FX_COLOR(18,34,54),255);
        if(v->row==4)fx_gloss(c,412,504,770,65,12,v->frame);
        fx_text(c,435,508,"Debug timestamp",1,FX_WHITE);
        fx_text(c,437,540,"Show elapsed time in game for matching the log.",0,FX_MUTED);
        fx_round(c,1080,519,72,32,16,v->timestamp?FX_COLOR(21,144,208):FX_COLOR(65,83,103),255);
        fx_circle(c,v->timestamp?1136:1096,535,12,FX_WHITE);
        fx_text(c,418,589,v->saved?"Settings saved. Ready to play.":"16:9 widescreen  /  VSync ON",0,v->saved?FX_BLUE:FX_MUTED);
    }
    fx_footer(c);
    fx_hint(c,56,689,"A",v->screen==FX_SETTINGS?(v->row==4?"Toggle":"Apply"):"Select");
    fx_hint(c,210,689,"B","Back");
    fx_hint(c,950,689,"+","Exit");fx_hint(c,1084,689,"H","HOME");
    if(v->screen==FX_LOADING||v->screen==FX_FAILED){
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
