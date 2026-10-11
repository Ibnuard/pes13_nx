/* SPDX-License-Identifier: LGPL-2.1-or-later. Successful verification receipt.
 * A few metadata reads replace full game-directory and runtime SHA scans.
 * This is a startup optimization, not a security or boot-patch credential. */
#ifndef FEXTENDO_STARTUP_CACHE_H
#define FEXTENDO_STARTUP_CACHE_H
#include <unistd.h>
#include "fextendo_install_check.h"
#include "fextendo_runtime_api.h"
#define FX_CHECK_CACHE_REV "0.4.1-gui1"
static const char *const fx_cache_anchors[]={
    "drive_c/PES13/pes2013.exe","drive_c/PES13/img",
    "drive_c/windows/system32/ntdll.dll","drive_c/windows/system32/libwow64fex.dll",
    "drive_c/windows/syswow64/ntdll.dll","launcher/font.bin","launcher/wordmark.rgba"
};
#define FX_CACHE_ANCHORS (sizeof(fx_cache_anchors)/sizeof(fx_cache_anchors[0]))
struct fx_cache_receipt {
    char revision[24],catalog[65],root[768];
    struct {uint64_t size,mtime;} anchor[FX_CACHE_ANCHORS];
};
static int fx_cache_expected(const char *root,struct fx_cache_receipt *r){
    char p[1024];struct stat st;memset(r,0,sizeof(*r));
    if(strlen(root)>=sizeof(r->root))return 0;
    snprintf(r->revision,sizeof(r->revision),"%s",FX_CHECK_CACHE_REV);
    snprintf(r->catalog,sizeof(r->catalog),"%s",fx_runtime_catalog_id());
    snprintf(r->root,sizeof(r->root),"%s",root);
    if(!fx_install_directory(root))return 0;
    /* Never hide an interrupted transaction, even with a valid old receipt. */
    if(!fx_install_path(p,sizeof(p),root,".runtime-fixer"))return 0;
    if(!lstat(p,&st)){if(!S_ISDIR(st.st_mode))return 0;}else if(errno!=ENOENT)return 0;
    const char *const journals[]={".runtime-fixer/plan",".runtime-fixer/done"};
    for(unsigned i=0;i<2;i++)
        if(!fx_install_path(p,sizeof(p),root,journals[i])||!lstat(p,&st)||errno!=ENOENT)return 0;
    for(unsigned i=0;i<FX_CACHE_ANCHORS;i++){
        if(!fx_install_path(p,sizeof(p),root,fx_cache_anchors[i])||lstat(p,&st))return 0;
        if(i==1?!S_ISDIR(st.st_mode):(!S_ISREG(st.st_mode)||st.st_size<=0))return 0;
        r->anchor[i].size=st.st_size;r->anchor[i].mtime=st.st_mtime;
    }
    return 1;
}
static int fx_startup_cache_valid(const char *root){
    char p[1024];struct stat st;struct fx_cache_receipt expected,found;
    if(!fx_cache_expected(root,&expected)||!fx_install_path(p,sizeof(p),root,"launcher/startup-verified.dat")||
       lstat(p,&st)||!S_ISREG(st.st_mode)||st.st_size!=sizeof(found))return 0;
    FILE *f=fopen(p,"rb");if(!f)return 0;
    int ok=fread(&found,1,sizeof(found),f)==sizeof(found)&&fgetc(f)==EOF&&!ferror(f);fclose(f);
    return ok&&!memcmp(&expected,&found,sizeof(found));
}
static int fx_startup_cache_clear(const char *root){
    char p[1024];return fx_install_path(p,sizeof(p),root,"launcher/startup-verified.dat")&&(!unlink(p)||errno==ENOENT);
}
static int fx_startup_cache_save(const char *root){
    char p[1024],tmp[1024];struct fx_cache_receipt expected;
    if(!fx_cache_expected(root,&expected)||!fx_install_path(p,sizeof(p),root,"launcher/startup-verified.dat")||
       !fx_install_path(tmp,sizeof(tmp),root,"launcher/startup-verified.tmp"))return 0;
    /* Never follow a stale temporary symlink. An interrupted save is a miss. */
    if(unlink(tmp)&&errno!=ENOENT)return 0;
    FILE *f=fopen(tmp,"wb");if(!f)return 0;
    int ok=fwrite(&expected,1,sizeof(expected),f)==sizeof(expected)&&!fflush(f)&&!fsync(fileno(f));
    if(fclose(f))ok=0;
    if(ok&&!rename(tmp,p))return 1;
    unlink(tmp);return 0;
}
#endif
