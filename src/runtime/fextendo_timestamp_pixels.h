/* LGPL-2.1-or-later. Small AA digit atlas with a built-in fallback. */
#ifndef FEXTENDO_TIMESTAMP_PIXELS_H
#define FEXTENDO_TIMESTAMP_PIXELS_H
#define FX_TIME_W 224
#define FX_TIME_H 32
static unsigned char fx_timestamp_font[14*14*28];
static int fx_timestamp_font_ready;
static void fx_timestamp_format(char text[32],uint64_t ms) {
    snprintf(text,32,"T+ %02u:%02u:%02u.%u",(unsigned)(ms/3600000%100),
             (unsigned)(ms/60000%60),(unsigned)(ms/1000%60),(unsigned)(ms/100%10));
}
static void fx_timestamp_pixels(uint32_t *pixels,unsigned stride,uint64_t ms) {
    static const unsigned char glyph[14][7]={
        {14,17,19,21,25,17,14},{4,12,4,4,4,4,14},{14,17,1,2,4,8,31},
        {30,1,1,14,1,1,30},{2,6,10,18,31,2,2},{31,16,16,30,1,1,30},
        {14,16,16,30,17,17,14},{31,1,2,4,8,8,8},{14,17,17,14,17,17,14},
        {14,17,17,15,1,1,14},{0,4,4,0,4,4,0},{0,0,0,0,0,4,4},
        {31,4,4,4,4,4,4},{0,4,4,31,4,4,0}};
    char text[32];fx_timestamp_format(text,ms);
    for(unsigned y=0;y<FX_TIME_H;y++)for(unsigned x=0;x<FX_TIME_W;x++)
        pixels[y*stride+x]=0xff140c06u;
    if(fx_timestamp_font_ready){
        for(unsigned i=0;text[i];i++){
            const char *chars="0123456789:.T+",*g=strchr(chars,text[i]);if(!g)continue;
            const unsigned char *mask=fx_timestamp_font+(g-chars)*14*28;
            for(unsigned y=0;y<28;y++)for(unsigned x=0;x<14;x++){
                unsigned a=mask[y*14+x],dx=10+i*14+x;if(dx>=FX_TIME_W)continue;
                uint32_t bg=0xff140c06u,col=i<2?0xffffc233u:0xfff8f6f0u;
                unsigned r=((bg&255)*(255-a)+(col&255)*a)/255;
                unsigned green=(((bg>>8)&255)*(255-a)+((col>>8)&255)*a)/255;
                unsigned b=(((bg>>16)&255)*(255-a)+((col>>16)&255)*a)/255;
                pixels[(y+2)*stride+dx]=r|(green<<8)|(b<<16)|0xff000000u;
            }
        }
        return;
    }
    for(unsigned i=0;text[i];i++){
        char ch=text[i];int g=ch>='0'&&ch<='9'?ch-'0':ch==':'?10:ch=='.'?11:ch=='T'?12:ch=='+'?13:-1;
        if(g<0)continue;
        for(unsigned y=0;y<7;y++)for(unsigned x=0;x<5;x++)if(glyph[g][y]&(1u<<(4-x)))
            for(unsigned yy=0;yy<2;yy++)for(unsigned xx=0;xx<2;xx++){
                unsigned dx=12+i*14+x*2+xx,dy=9+y*2+yy;
                if(dx<FX_TIME_W)pixels[dy*stride+dx]=i<2?0xffffc233u:0xfff8f6f0u;
            }
    }
}
#endif
