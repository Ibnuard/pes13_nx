/* SPDX-License-Identifier: LGPL-2.1-or-later. Embedded, SD-independent GUI. */
#ifndef FEXTENDO_STARTUP_ART_H
#define FEXTENDO_STARTUP_ART_H
extern const unsigned char fx_boot_font[],fx_boot_wordmark[];
extern const unsigned fx_boot_font_size,fx_boot_wordmark_size;
static int fx_boot_art_load(struct fx_art *a){
    memset(a,0,sizeof(*a));fx_prepare_motion(a);
    a->font=malloc(fx_boot_font_size);a->wordmark=malloc(fx_boot_wordmark_size);
    a->scene[0]=malloc(FX_W*FX_H*4);a->scene[3]=malloc(FX_W*FX_H*4);
    if(!a->font||!a->wordmark||!a->scene[0]||!a->scene[3]){fx_art_free(a);return 0;}
    a->font_size=fx_boot_font_size;memcpy(a->font,fx_boot_font,fx_boot_font_size);
    memcpy(a->wordmark,fx_boot_wordmark,fx_boot_wordmark_size);
    for(int y=0;y<FX_H;y++)for(int x=0;x<FX_W;x++){
        float dx=(x-640)/320.f,dy=(y-350)/190.f;
        a->scene[3][y*FX_W+x]=fx_blend(FX_COLOR(3,8,17),FX_COLOR(7,39,76),(unsigned)(fx_decay(a,dx*dx+dy*dy)*145));
    }
    memcpy(a->scene[0],a->scene[3],FX_W*FX_H*4);
    struct fx_canvas c={a->scene[0],FX_W,a};
    fx_image(&c,a->wordmark,600,128,46,25,230,49,0,255);
    fx_text(&c,49,669,"PES13  /  " FX_APP_VERSION,0,FX_MUTED);
    fx_text(&c,982,669,"AndroSwitch Project",0,FX_MUTED);
    return 1;
}
static void fx_check_draw(struct fx_canvas *c,const struct fx_view *v){
    const struct fx_check_view *s=&v->check;
    static const char *const phases[]={"Checking boot environment","Checking game installation","Checking runtime files",
        "Downloading runtime","Verifying download","Installing runtime","Recovering runtime","Preparing launcher"};
    const char *labels[]={"Boot environment","Game installation","Runtime files"};
    int done[]={s->memory_done,s->game_done,s->runtime_done};
    fx_rect(c,0,0,FX_W,FX_H,FX_COLOR(1,7,17),135);
    fx_round(c,247,113,786,517,27,FX_COLOR(51,79,108),230);
    fx_round(c,249,115,782,513,25,FX_COLOR(12,26,44),255);
    fx_text(c,290,146,s->failed?"Setup needs attention":"Getting ready",2,FX_WHITE);
    fx_text(c,291,202,s->cached?"Previous verification saved. Checking this boot.":"Checking your installation before you play.",0,FX_MUTED);
    for(int i=0;i<3;i++){
        int y=258+i*51;
        fx_circle(c,302,y+13,10,done[i]?FX_COLOR(49,176,136):FX_COLOR(46,65,85));
        fx_text(c,328,y,labels[i],0,FX_WHITE);
        const char *status=done[i]?(i==0?(v->boot_patch?"Patch active / High ready":"High locked"):s->cached?"Verified previously":"Ready"):"Waiting";
        fx_text(c,642,y,status,0,done[i]?FX_MUTED:FX_COLOR(120,141,164));
    }
    if(s->failed){
        fx_wrapped(c,291,423,s->error,696);
        fx_round(c,288,553,282,47,13,FX_COLOR(28,71,118),255);
        fx_text(c,331,565,"A  Retry checks",0,FX_WHITE);
        fx_text(c,675,565,"B / +  Close launcher",0,FX_MUTED);
    }else{
        char line[96];snprintf(line,sizeof(line),"%s%s",phases[s->phase],s->percent<0?"...":"");
        fx_text(c,291,430,line,0,FX_WHITE);
        if(s->percent>=0){char percent[12];snprintf(percent,sizeof(percent),"%d%%",s->percent);fx_text(c,928,430,percent,0,FX_BLUE);}
        fx_round(c,291,474,698,5,2,FX_COLOR(35,55,77),255);
        int width=s->percent>=0?s->percent*698/100:140;
        int x=s->percent>=0?291:291+(int)(v->frame%160<80?v->frame%160:160-v->frame%160)*6;
        if(width)fx_round(c,x,474,width,5,2,FX_BLUE,255);
        fx_text(c,291,516,"Missing runtime files are repaired automatically.",0,FX_MUTED);
        fx_text(c,291,559,"Please wait. The launcher opens when setup is ready.",0,FX_MUTED);
    }
}
#endif
