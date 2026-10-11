/* SPDX-License-Identifier: LGPL-2.1-or-later. Read-only installation validation.
 * Game contents are never downloaded, repaired or hashed by the runtime fixer. */
#ifndef FEXTENDO_INSTALL_CHECK_H
#define FEXTENDO_INSTALL_CHECK_H
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <strings.h>
#include <ctype.h>
#include <dirent.h>
#include <sys/stat.h>
#include <errno.h>

static int fx_install_path(char *out,size_t cap,const char *root,const char *name){
    int n=snprintf(out,cap,"%s/%s",root,name);return n>0&&(size_t)n<cap;
}
static int fx_install_directory(const char *p){
    struct stat st;return !lstat(p,&st)&&S_ISDIR(st.st_mode);
}
static int fx_install_file(const char *p){
    struct stat st;return !lstat(p,&st)&&S_ISREG(st.st_mode)&&st.st_size>0;
}
static int fx_install_error(char *out,size_t cap,const char *text){
    snprintf(out,cap,"Installation is not correct. %s",text);return 0;
}
static uint32_t fx_install_u32(const unsigned char *b){
    return (uint32_t)b[0]|(uint32_t)b[1]<<8|(uint32_t)b[2]<<16|(uint32_t)b[3]<<24;
}
/* Validate AFS directory entries, not multi-GB payloads. Sizes vary with
 * language and patches; only each entry's bounds within its own file matter.
 * Empty entries occur in the real game and need no backing payload. */
static int fx_install_archive(const char *path){
    struct stat st;unsigned char header[8],entries[4096];
    if(lstat(path,&st))return errno==ENOENT?0:-1;
    if(!S_ISREG(st.st_mode)||st.st_size<8)return -1;
    FILE *f=fopen(path,"rb");if(!f)return -1;
    int valid=0;
    if(fread(header,1,sizeof(header),f)==sizeof(header)&&!memcmp(header,"AFS\0",4)){
        uint32_t remaining=fx_install_u32(header+4);
        uint64_t end=8+(uint64_t)remaining*8;
        /* Bound work even for a corrupt count. The reference game has at most
         * 17,323 entries in one archive; permit up to a million for mods. */
        valid=remaining>0&&remaining<=1048576&&end<=(uint64_t)st.st_size;
        while(valid&&remaining){
            unsigned count=remaining>512?512:remaining;
            if(fread(entries,8,count,f)!=count){valid=0;break;}
            for(unsigned i=0;i<count;i++){
                uint32_t offset=fx_install_u32(entries+i*8),size=fx_install_u32(entries+i*8+4);
                if(size&&(offset<end||(uint64_t)offset+size>(uint64_t)st.st_size)){valid=0;break;}
            }
            remaining-=count;
        }
    }
    fclose(f);return valid?1:-1;
}
static int fx_install_archive_error(char *error,size_t cap,const char *name,int result){
    char detail[512];
    snprintf(detail,sizeof(detail),result==0?"Missing img/%s. Copy the complete img folder.":
        "Unreadable or incomplete img/%s. Recopy this file from the game.",name);
    return fx_install_error(error,cap,detail);
}
static int fx_install_locale_name(const char *name,const char *prefix){
    size_t n=strlen(name);
    if(n<10||strncasecmp(name,prefix,5)||strcasecmp(name+n-4,".img"))return 0;
    for(size_t i=5;i<n-4;i++)if(!isalnum((unsigned char)name[i])&&name[i]!='_'&&name[i]!='-')return 0;
    return 1;
}
static int fx_install_game(const char *game,char *error,size_t cap){
    char path[1024];unsigned char dos[64],pe[26];struct stat st;
    error[0]=0;
    if(!fx_install_directory(game))return fx_install_error(error,cap,
        "Put the game in /switch/pes13-fex/drive_c/PES13.");
    if(!fx_install_path(path,sizeof(path),game,"pes2013.exe")||!fx_install_file(path))
        return fx_install_error(error,cap,"Missing drive_c/PES13/pes2013.exe. Copy the complete game folder.");
    FILE *f=fopen(path,"rb");int valid=0;
    if(f){
        if(!fstat(fileno(f),&st)&&fread(dos,1,sizeof(dos),f)==sizeof(dos)&&dos[0]=='M'&&dos[1]=='Z'){
            uint32_t at=fx_install_u32(dos+60);
            if(at>=sizeof(dos)&&(uint64_t)at+sizeof(pe)<=(uint64_t)st.st_size&&
               !fseek(f,(long)at,SEEK_SET)&&fread(pe,1,sizeof(pe),f)==sizeof(pe))
                valid=!memcmp(pe,"PE\0\0",4)&&pe[4]==0x4c&&pe[5]==1&&pe[24]==0x0b&&pe[25]==1;
        }
        fclose(f);
    }
    if(!valid)return fx_install_error(error,cap,"pes2013.exe is unreadable or is not a valid 32-bit Windows executable.");
    char img[1024];
    if(!fx_install_path(img,sizeof(img),game,"img")||!fx_install_directory(img))
        return fx_install_error(error,cap,"Missing or invalid drive_c/PES13/img folder. Copy the complete img folder.");
    static const char *const archives[]={"dt01.img","dt02.img","dt03.img","dt04.img",
        "dt06.img","dt07.img","dt08.img","dt09.img","dt0a.img","dt0b.img","dt0c.img",
        "dt0d.img","dt0e.img","dt0f.img","dt10.img","dt11.img"};
    for(unsigned i=0;i<sizeof(archives)/sizeof(archives[0]);i++){
        if(!fx_install_path(path,sizeof(path),img,archives[i]))return fx_install_error(error,cap,"Game path is too long.");
        int result=fx_install_archive(path);
        if(result!=1)return fx_install_archive_error(error,cap,archives[i],result);
    }
    /* Commentary and menu language can differ. Do not require English or every
     * language shipped by the reference PC installation. */
    DIR *dir=opendir(img);if(!dir)return fx_install_error(error,cap,"Cannot read the game's img folder. Check the SD card.");
    int languages[2]={0,0};char invalid[2][256]={{0},{0}};struct dirent *entry;
    while((entry=readdir(dir))){
        int kind=fx_install_locale_name(entry->d_name,"dt00_")?0:fx_install_locale_name(entry->d_name,"dt05_")?1:-1;
        if(kind<0||languages[kind])continue;
        if(!fx_install_path(path,sizeof(path),img,entry->d_name))continue;
        if(fx_install_archive(path)==1)languages[kind]=1;
        else if(!invalid[kind][0])snprintf(invalid[kind],sizeof(invalid[kind]),"%s",entry->d_name);
    }
    closedir(dir);
    for(unsigned i=0;i<2;i++)if(!languages[i]){
        if(invalid[i][0])return fx_install_archive_error(error,cap,invalid[i],-1);
        return fx_install_error(error,cap,i==0?
            "Missing commentary data img/dt00_*.img (for example dt00_e.img). Copy the complete img folder.":
            "Missing menu language data img/dt05_*.img (for example dt05_e.img). Copy the complete img folder.");
    }
    return 1;
}
static int fx_install_check(const char *root,char *error,size_t cap){
    char path[1024];struct stat st;
    error[0]=0;
    if(!fx_install_directory(root))return fx_install_error(error,cap,
        "Copy switch/pes13-fex to the SD root; avoid an extra nested switch folder.");
    if(!fx_install_path(path,sizeof(path),root,"drive_c")||!fx_install_directory(path))
        return fx_install_error(error,cap,"Put the drive_c folder directly inside /switch/pes13-fex.");
    if(!fx_install_path(path,sizeof(path),root,"drive_c/PES13"))return fx_install_error(error,cap,"Game path is too long.");
    if(!fx_install_game(path,error,cap))return 0;
    /* Missing runtime directories can be restored. A file/symlink in their
     * place is an installation error, never a destination for extraction. */
    static const char *const directories[]={"drive_c/windows","drive_c/windows/system32",
        "drive_c/windows/syswow64","share","launcher"};
    for(unsigned i=0;i<sizeof(directories)/sizeof(directories[0]);i++){
        if(!fx_install_path(path,sizeof(path),root,directories[i]))return 0;
        if(!lstat(path,&st)){if(!S_ISDIR(st.st_mode))return fx_install_error(error,cap,"A runtime folder is a file or link. Recopy the package with its folder structure.");}
        else if(errno!=ENOENT)return fx_install_error(error,cap,"A runtime folder cannot be read. Check the SD card.");
    }
    return 1;
}
#endif
