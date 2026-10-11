/* SPDX-License-Identifier: LGPL-2.1-or-later. Read-only installation validation.
 * Game contents are never downloaded, repaired or hashed by the runtime fixer. */
#ifndef FEXTENDO_INSTALL_CHECK_H
#define FEXTENDO_INSTALL_CHECK_H
#include <stdio.h>
#include <stdint.h>
#include <string.h>
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
static int fx_install_check(const char *root,char *error,size_t cap){
    char path[1024];unsigned char dos[64],pe[26];struct stat st;
    error[0]=0;
    if(!fx_install_directory(root))return fx_install_error(error,cap,
        "Copy switch/pes13-fex to the SD root; avoid an extra nested switch folder.");
    if(!fx_install_path(path,sizeof(path),root,"drive_c")||!fx_install_directory(path))
        return fx_install_error(error,cap,"Put the drive_c folder directly inside /switch/pes13-fex.");
    if(!fx_install_path(path,sizeof(path),root,"drive_c/PES13")||!fx_install_directory(path))
        return fx_install_error(error,cap,"Put the game in /switch/pes13-fex/drive_c/PES13.");
    if(!fx_install_path(path,sizeof(path),root,"drive_c/PES13/pes2013.exe")||!fx_install_file(path))
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
    if(!fx_install_path(path,sizeof(path),root,"drive_c/PES13/img/dt00.img")||!fx_install_file(path))
        return fx_install_error(error,cap,"Missing drive_c/PES13/img/dt00.img. Copy the complete img folder.");
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
