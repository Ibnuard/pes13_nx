/* LGPL-2.1-or-later. Preset writes complete before the guest can start. */
#ifndef FEXTENDO_PRESETS_H
#define FEXTENDO_PRESETS_H
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include <errno.h>
#include <time.h>
#include "fextendo_keyboard_options.h"

static const char *const fx_preset_ids[4] = {"medium-720","low-720","extra-low-540","high-720"};
static const char *const fx_preset_names[4] = {"Medium 720p","Low 720p","Extra Low 540p","High 720p"};
static const char *const fx_preset_details[4] = {"1280 x 720  /  Balanced detail","1280 x 720  /  Reduced detail","960 x 540  /  Low detail","1280 x 720  /  Maximum detail"};
static const char *const fx_targets[5] = {
    "/drive_c/KONAMI/Pro Evolution Soccer 2013/settings.dat",
    "/drive_c/PES13/settings.dat",
    "/drive_c/users/steamuser/Documents/KONAMI/Pro Evolution Soccer 2013/settings.dat",
    "/drive_c/PES13/dxvk.conf", "/launcher/selected.txt"};
static uint32_t fx_u32(const unsigned char *p) { return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24; }
static uint16_t fx_crc(const unsigned char *d) {
    unsigned v=0,i,j;
    for(i=0;i<852;i++){v^=(unsigned)((i==12||i==13)?0:d[i])<<8;
        for(j=0;j<8;j++)v=((v<<1)^((v&32768)?0x1021:0))&65535;}
    return (uint16_t)~v;
}
static int fx_valid_settings(const unsigned char *d,size_t n) {
    return n==852 && fx_u32(d)==0x46434557 && fx_u32(d+4)==2 && fx_u32(d+8)==852 &&
        ((unsigned)d[12]|(unsigned)d[13]<<8)==fx_crc(d);
}
static size_t fx_read(const char *path,void *data,size_t cap) {
    FILE *f=fopen(path,"rb");size_t n;if(!f)return 0;
    n=fread(data,1,cap,f);if(ferror(f)||fgetc(f)!=EOF)n=0;fclose(f);return n;
}
static int fx_write(const char *path,const void *data,size_t size) {
    FILE *f=fopen(path,"wb");int ok;if(!f)return 0;
    ok=fwrite(data,1,size,f)==size && !fflush(f) && !fsync(fileno(f));
    if(fclose(f))ok=0;
    return ok;
}
static int fx_mkdir_parents(const char *path) {
    char p[768];size_t i;if(strlen(path)>=sizeof(p))return 0;strcpy(p,path);
    for(i=1;p[i];i++)if(p[i]=='/' && p[i-1]!=':'){
        p[i]=0;if(mkdir(p,0777)&&errno!=EEXIST)return 0;p[i]='/';}
    return 1;
}
static int fx_keyboard_options_read(const char *path,struct fx_keyboard_options *out) {
    char data[128]={0};unsigned shortcut,top;int end=0;
    size_t n=fx_read(path,data,sizeof(data)-1);
    if(!n||sscanf(data,"[keyboard]\nshortcut=%u\ntop=%u\n%n",&shortcut,&top,&end)!=2||
       end!=(int)n||shortcut>=FX_KEYBOARD_SHORTCUTS||top>1)return 0;
    *out=(struct fx_keyboard_options){(int)shortcut,(int)top};return 1;
}
static struct fx_keyboard_options fx_keyboard_options_load(const char *root) {
    struct fx_keyboard_options out={0};char path[800];
    snprintf(path,sizeof(path),"%s/launcher/keyboard.ini",root);
    if(fx_keyboard_options_read(path,&out))return out;
    snprintf(path,sizeof(path),"%s/launcher/keyboard.ini.old",root);
    fx_keyboard_options_read(path,&out);return out;
}
static int fx_keyboard_options_save(const char *root,struct fx_keyboard_options value) {
    char path[768],old[800],tmp[800],text[80];struct fx_keyboard_options previous;
    if(value.shortcut<0||value.shortcut>=FX_KEYBOARD_SHORTCUTS||value.top<0||value.top>1)return 0;
    snprintf(path,sizeof(path),"%s/launcher/keyboard.ini",root);
    snprintf(old,sizeof(old),"%s.old",path);snprintf(tmp,sizeof(tmp),"%s.new",path);
    int n=snprintf(text,sizeof(text),"[keyboard]\nshortcut=%d\ntop=%d\n",value.shortcut,value.top);
    if(!fx_mkdir_parents(path)||!fx_write(tmp,text,(size_t)n))return 0;
    if(fx_keyboard_options_read(path,&previous)){
        if(unlink(old)&&errno!=ENOENT)return 0;
        if(rename(path,old))return 0;
    }else if(unlink(path)&&errno!=ENOENT)return 0;
    if(rename(tmp,path)){rename(old,path);return 0;}
    unlink(old);return 1;
}
/* A small journal makes an interrupted multi-file update recoverable on restart.
 * The game is never allowed to launch while recovery is incomplete. */
static int fx_recover(const char *root) {
    char journal[768],path[768],old[800],tmp[800];unsigned char mask;int i;
    snprintf(journal,sizeof(journal),"%s/launcher/preset.txn",root);
    if(access(journal,F_OK))return errno==ENOENT;
    if(fx_read(journal,&mask,1)!=1 || mask&~31)return 0;
    for(i=0;i<5;i++){
        snprintf(path,sizeof(path),"%s%s",root,fx_targets[i]);
        snprintf(old,sizeof(old),"%s.fxt-old",path);snprintf(tmp,sizeof(tmp),"%s.fxt-new",path);
        if(!access(old,F_OK)) {
            /* Horizon's rename does not replace an existing destination. */
            if(unlink(path)&&errno!=ENOENT)return 0;
            if(rename(old,path))return 0;
        }
        else if(!(mask&(1u<<i)) && unlink(path) && errno!=ENOENT)return 0;
        else if((mask&(1u<<i)) && access(path,F_OK))return 0;
        unlink(tmp);
    }
    return !unlink(journal);
}
static int fx_selected(const char *root) {
    char path[768],b[8]={0};snprintf(path,sizeof(path),"%s/launcher/selected.txt",root);
    return fx_read(path,b,7)==2 && b[0]>='0' && b[0]<='3' && b[1]=='\n' ? b[0]-'0':0;
}
static int fx_menu_sound(const char *root) {
    char p[768],b[2];snprintf(p,sizeof(p),"%s/launcher/menu-sound.txt",root);
    return fx_read(p,b,2)!=2||b[0]!='0'||b[1]!='\n';
}
static int fx_menu_sound_save(const char *root,int on) {
    char p[768];snprintf(p,sizeof(p),"%s/launcher/menu-sound.txt",root);
    return fx_write(p,on?"1\n":"0\n",2);
}
static int fx_background_music(const char *root) {
    char p[768],b[2];snprintf(p,sizeof(p),"%s/launcher/background-music.txt",root);
    return fx_read(p,b,2)!=2||b[0]!='0'||b[1]!='\n';
}
static int fx_background_music_save(const char *root,int on) {
    char p[768];snprintf(p,sizeof(p),"%s/launcher/background-music.txt",root);
    return fx_write(p,on?"1\n":"0\n",2);
}
static uint64_t fx_last_played(const char *root) {
    char path[768],text[32];snprintf(path,sizeof(path),"%s/launcher/last-played.txt",root);
    size_t n=fx_read(path,text,sizeof(text));uint64_t value=0;
    if(n<2||n>11||text[n-1]!='\n')return 0;
    for(size_t i=0;i<n-1;i++){if(text[i]<'0'||text[i]>'9')return 0;value=value*10+text[i]-'0';}
    return value>=946684800ull&&value<=4102444800ull?value:0;
}
static int fx_last_played_save(const char *root,uint64_t timestamp) {
    if(timestamp<946684800ull||timestamp>4102444800ull)return 0;
    char path[768],text[32];snprintf(path,sizeof(path),"%s/launcher/last-played.txt",root);
    int n=snprintf(text,sizeof(text),"%llu\n",(unsigned long long)timestamp);
    return fx_write(path,text,(size_t)n);
}
static void fx_last_played_label(char text[48],uint64_t played,uint64_t now) {
    if(!played){snprintf(text,48,"Never");return;}
    if(now<played||now<946684800ull){snprintf(text,48,"Recently");return;}
    uint64_t seconds=now-played,value;const char *unit;
    if(seconds<60){snprintf(text,48,"Just now");return;}
    if(seconds<3600){value=seconds/60;unit="minute";}
    else if(seconds<86400){value=seconds/3600;unit="hour";}
    else if(seconds<2592000){value=seconds/86400;unit="day";}
    else if(seconds<31536000){value=seconds/2592000;unit="month";}
    else{value=seconds/31536000;unit="year";}
    snprintf(text,48,"%llu %s%s ago",(unsigned long long)value,unit,value==1?"":"s");
}
static int fx_debug_timestamp(const char *root) {
    char p[768],b[2];snprintf(p,sizeof(p),"%s/launcher/debug-timestamp.txt",root);
    return fx_read(p,b,2)==2&&b[0]=='1'&&b[1]=='\n';
}
static int fx_debug_timestamp_save(const char *root,int on) {
    char p[768];snprintf(p,sizeof(p),"%s/launcher/debug-timestamp.txt",root);
    return fx_write(p,on?"1\n":"0\n",2);
}
static int fx_debug_launch(const char *root) {
    char p[768],b[2];snprintf(p,sizeof(p),"%s/launcher/debug-launch.txt",root);
    return fx_read(p,b,2)==2&&b[0]=='1'&&b[1]=='\n';
}
static int fx_debug_launch_save(const char *root,int on) {
    char p[768];snprintf(p,sizeof(p),"%s/launcher/debug-launch.txt",root);
    return fx_write(p,on?"1\n":"0\n",2);
}
static int fx_apply_preset(const char *root,int selected) {
    unsigned char data[5][4096],mask=0;size_t sizes[5];
    char path[5][768],tmp[5][800],old[5][800],source[768],journal[768],journal_tmp[800];
    unsigned char templ[852],canonical[852];int i;size_t n;
    if(selected<0||selected>3||!fx_recover(root))return 0;
    snprintf(source,sizeof(source),"%s/launcher/presets/%s.dat",root,fx_preset_ids[selected]);
    if(fx_read(source,templ,sizeof(templ))!=852||!fx_valid_settings(templ,852))return 0;
    if(fx_u32(templ+16)!=(selected==2?960u:1280u)||fx_u32(templ+20)!=(selected==2?540u:720u)||
       fx_u32(templ+24)!=1||fx_u32(templ+28)!=(selected==0?1u:selected==3?2u:0u)||!(templ[14]&1))return 0;
    snprintf(journal,sizeof(journal),"%s/launcher/preset.txn",root);
    snprintf(journal_tmp,sizeof(journal_tmp),"%s.tmp",journal);
    snprintf(source,sizeof(source),"%s%s",root,fx_targets[0]);
    n=fx_read(source,canonical,sizeof(canonical));
    if(!fx_valid_settings(canonical,n))memcpy(canonical,templ,852);
    for(i=0;i<5;i++){
        snprintf(path[i],sizeof(path[i]),"%s%s",root,fx_targets[i]);
        snprintf(tmp[i],sizeof(tmp[i]),"%.*s.fxt-new",767,path[i]);
        snprintf(old[i],sizeof(old[i]),"%.*s.fxt-old",767,path[i]);
        if(!fx_mkdir_parents(path[i]))return 0;
        if(!access(path[i],F_OK))mask|=1u<<i;
        if(i<3){
            memcpy(data[i],canonical,852);
            data[i][14]|=1; /* VSync; preserve other controller/display flags. */
            data[i][15]|=2; /* Global PES XInput flag 0x0200, for both native slots. */
            memcpy(data[i]+16,templ+16,16); /* resolution, 16:9, quality */
            uint16_t crc=fx_crc(data[i]);data[i][12]=crc;data[i][13]=crc>>8;sizes[i]=852;
        } else if(i==3){
            snprintf(source,sizeof(source),"%s/launcher/presets/dxvk.conf",root);
            sizes[i]=fx_read(source,data[i],sizeof(data[i])-1);
            if(!sizes[i])return 0;
            data[i][sizes[i]]=0;
            if(!strstr((char*)data[i],"d3d9.presentInterval = 1\n"))return 0;
        } else {data[i][0]='0'+selected;data[i][1]='\n';sizes[i]=2;}
    }
    /* An ordinary launch verifies settings without rewriting five files and
     * their transaction journal. Preserve canonical controller edits above. */
    int unchanged=1;
    for(i=0;i<5;i++){
        unsigned char existing[4096];
        if(fx_read(path[i],existing,sizeof(existing))!=sizes[i]||memcmp(existing,data[i],sizes[i]))unchanged=0;
    }
    if(unchanged)return 1;
    for(i=0;i<5;i++)if(!fx_write(tmp[i],data[i],sizes[i]))goto stage_failed;
    /* Remove only stale backups left after a committed transaction. */
    for(i=0;i<5;i++)if(unlink(old[i])&&errno!=ENOENT)goto stage_failed;
    if(!fx_write(journal_tmp,&mask,1)||rename(journal_tmp,journal)){unlink(journal_tmp);goto stage_failed;}
    for(i=0;i<5;i++){
        if((mask&(1u<<i))&&rename(path[i],old[i]))goto rollback;
        if(rename(tmp[i],path[i]))goto rollback;
    }
    if(unlink(journal))goto rollback;
    for(i=0;i<5;i++)unlink(old[i]);
    return 1;
rollback:
    fx_recover(root);return 0;
stage_failed:
    for(i=0;i<5;i++)unlink(tmp[i]);
    return 0;
}
#endif
