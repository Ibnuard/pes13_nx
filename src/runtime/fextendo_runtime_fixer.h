/* LGPL-2.1-or-later. Manual runtime repair. No guest/game paths or background I/O.
 * The catalog is compiled into the NRO, never supplied by the download. */
#ifndef FEXTENDO_RUNTIME_FIXER_H
#define FEXTENDO_RUNTIME_FIXER_H
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <sys/stat.h>
#include <minizip/unzip.h>
#include "fextendo_runtime_api.h"
#ifdef __SWITCH__
#include <switch.h>
#else
#include <openssl/sha.h>
typedef SHA256_CTX Sha256Context;
static void sha256ContextCreate(Sha256Context *c){SHA256_Init(c);}
static void sha256ContextUpdate(Sha256Context *c,const void *p,size_t n){SHA256_Update(c,p,n);}
static void sha256ContextGetHash(Sha256Context *c,void *p){SHA256_Final(p,c);}
#endif
struct fxr_file {const char *path;uint64_t size;const char *hash;};
#ifdef FXR_TEST_DEFINE
FXR_TEST_DEFINE
#endif
#ifndef FXR_TEST_CATALOG
#include "fextendo_runtime_catalog.h"
#endif
#ifndef FXR_SYNC
#ifdef __SWITCH__
#define FXR_SYNC() R_SUCCEEDED(fsdevCommitDevice("sdmc"))
#else
#define FXR_SYNC() 1
#endif
#endif
#ifndef FXR_RENAME
#define FXR_RENAME(a,b) rename(a,b)
#endif
#ifndef FXR_UNLINK
#define FXR_UNLINK(a) unlink(a)
#endif
typedef char fxr_catalog_capacity_check[FXR_COUNT<=sizeof(((struct fxr_job *)0)->flags)?1:-1];
static int fxr_error(struct fxr_job *j,const char *s){snprintf(j->error,sizeof(j->error),"%s",s);return 0;}
static int fxr_cancel(struct fxr_job *j){return j->cancelled&&j->cancelled();}
static void fxr_progress(struct fxr_job *j,int phase,uint64_t n,uint64_t total,const char *s){if(j->progress)j->progress(phase,n,total,s);}
static int fxr_path(char *out,size_t capacity,const char *root,const char *relative){
    int n=snprintf(out,capacity,"%s/%s",root,relative);return n>0&&(size_t)n<capacity;
}
static int fxr_slot(char *out,size_t capacity,const char *root,unsigned index,const char *suffix){
    int n=snprintf(out,capacity,"%s/.runtime-fixer/%03u.%s",root,index,suffix);return n>0&&(size_t)n<capacity;
}
/* Parents may be created, but a symlink or non-directory must never redirect writes. */
static int fxr_parents(const char *path,int create){
    char p[1024];struct stat st;size_t n=strlen(path);if(n>=sizeof(p))return 0;
    memcpy(p,path,n+1);
    for(char *s=p+1;*s;s++)if(*s=='/'){
        if(s[-1]==':')continue; /* libnx device root, e.g. sdmc:/ */
        *s=0;
        if(lstat(p,&st)){
            if(errno!=ENOENT)return 0;
            if(create&&mkdir(p,0777)&&errno!=EEXIST)return 0;
        }else if(!S_ISDIR(st.st_mode))return 0;
        *s='/';
    }
    return 1;
}
static int fxr_exists(const char *p){struct stat st;if(lstat(p,&st))return errno==ENOENT?0:-1;return S_ISREG(st.st_mode)?1:-1;}
static void fxr_digest(const void *p,size_t n,unsigned char hash[32]){Sha256Context c;sha256ContextCreate(&c);sha256ContextUpdate(&c,p,n);sha256ContextGetHash(&c,hash);}
static void fxr_hex(const unsigned char hash[32],char text[65]){static const char h[]="0123456789abcdef";for(int i=0;i<32;i++){text[2*i]=h[hash[i]>>4];text[2*i+1]=h[hash[i]&15];}text[64]=0;}
static int fxr_matches(const char *p,uint64_t size,const char *expected,struct fxr_job *job){
    struct stat st;if(!fxr_parents(p,0)||lstat(p,&st)||!S_ISREG(st.st_mode)||(uint64_t)st.st_size!=size)return 0;
    FILE *f=fopen(p,"rb");if(!f)return 0;
    Sha256Context c;unsigned char buffer[32768],hash[32];char hex[65];size_t n;uint64_t read=0;int ok=1;
    sha256ContextCreate(&c);
    while((n=fread(buffer,1,sizeof(buffer),f))){
        read+=n;if(read>size||(job&&fxr_cancel(job))){ok=0;break;}
        sha256ContextUpdate(&c,buffer,n);
    }
    if(ferror(f)||read!=size)ok=0;
    fclose(f);sha256ContextGetHash(&c,hash);fxr_hex(hash,hex);return ok&&!strcmp(hex,expected);
}
static int fxr_write(const char *p,const void *data,size_t n){
    if(!fxr_parents(p,1)||fxr_exists(p)<0)return 0;
    FILE *f=fopen(p,"wb");if(!f)return 0;
    int ok=fwrite(data,1,n,f)==n&&!fflush(f)&&!fsync(fileno(f));
    if(fclose(f))ok=0;
    return ok;
}
static int fxr_remove(const char *p){return !FXR_UNLINK(p)||errno==ENOENT;}
#define FXR_PLAN_SIZE (8+64+FXR_COUNT+32)
static int fxr_plan_read(const char *p,unsigned char flags[FXR_COUNT]){
    unsigned char data[FXR_PLAN_SIZE],hash[32];int extra;
    if(!fxr_parents(p,0)||fxr_exists(p)!=1)return 0;
    FILE *f=fopen(p,"rb");if(!f)return 0;
    size_t n=fread(data,1,sizeof(data),f);extra=fgetc(f);int ok=!ferror(f);fclose(f);
    if(!ok||n!=sizeof(data)||extra!=EOF||memcmp(data,"FXR1PLAN",8)||memcmp(data+8,FXR_CATALOG_ID,64))return 0;
    fxr_digest(data,sizeof(data)-32,hash);if(memcmp(hash,data+sizeof(data)-32,32))return 0;
    for(unsigned i=0;i<FXR_COUNT;i++)if(data[72+i]!=0&&data[72+i]!=1&&data[72+i]!=3)return 0;
    memcpy(flags,data+72,FXR_COUNT);return 1;
}
static int fxr_plan_write(const char *p,const unsigned char flags[FXR_COUNT]){
    unsigned char data[FXR_PLAN_SIZE];memcpy(data,"FXR1PLAN",8);memcpy(data+8,FXR_CATALOG_ID,64);
    memcpy(data+72,flags,FXR_COUNT);fxr_digest(data,sizeof(data)-32,data+sizeof(data)-32);
    return fxr_write(p,data,sizeof(data));
}
static int fxr_clean(const char *root){
    char p[1024];for(unsigned i=0;i<FXR_COUNT;i++)for(int s=0;s<2;s++){
        if(!fxr_slot(p,sizeof(p),root,i,s?"old":"new")||!fxr_remove(p))return 0;
    }
    return FXR_SYNC();
}
/* A journal is durable before any replacement. Until the commit marker is
 * durable, recovery restores the entire old set. Recovery is itself idempotent. */
static int fxr_recover(struct fxr_job *j){
    char plan[1024],done[1024],p[1024],old[1024];unsigned char flags[FXR_COUNT];
    if(!fxr_path(plan,sizeof(plan),j->root,".runtime-fixer/plan")||!fxr_path(done,sizeof(done),j->root,".runtime-fixer/done")||!fxr_parents(plan,0))return fxr_error(j,"Runtime recovery path is invalid.");
    int pending=fxr_exists(plan),committed=fxr_exists(done);
    if(pending<0||committed<0||(pending&&committed))return fxr_error(j,"Runtime recovery metadata is invalid. Keep the repair folder.");
    if(!pending&&!committed)return 1; /* Normal launch: no writes. */
    if(!fxr_plan_read(pending?plan:done,flags))return fxr_error(j,"Repair belongs to another runtime or is damaged. Use the same NRO to recover.");
    if(pending)for(unsigned i=0;i<FXR_COUNT;i++)if(flags[i]&1){
        fxr_progress(j,FXR_RECOVER,i,FXR_COUNT,fxr_files[i].path);
        if(!fxr_path(p,sizeof(p),j->root,fxr_files[i].path)||!fxr_slot(old,sizeof(old),j->root,i,"old")||!fxr_parents(p,0))return 0;
        int exists=fxr_exists(old);if(exists<0)return 0;
        if(exists){if(!fxr_remove(p)||FXR_RENAME(old,p)||!FXR_SYNC())return fxr_error(j,"Could not restore runtime backup. Check the SD card.");}
        else if(flags[i]&2){if(fxr_exists(p)!=1)return fxr_error(j,"Runtime backup is missing. Keep the repair folder.");}
        else if(!fxr_remove(p)||!FXR_SYNC())return 0;
    }
    /* Rollback must finish before deleting its journal or any remaining stages. */
    if(pending&&(!fxr_remove(plan)||!FXR_SYNC()))return 0;
    if(!fxr_clean(j->root))return fxr_error(j,"Repair cleanup failed. Check SD card space.");
    if(committed&&(!fxr_remove(done)||!FXR_SYNC()))return 0;
    return 1;
}
static int fxr_check(struct fxr_job *j){
    char p[1024];j->changed=0;memset(j->flags,0,sizeof(j->flags));
    for(unsigned i=0;i<FXR_COUNT;i++){
        if(fxr_cancel(j))return fxr_error(j,"Check cancelled. Runtime unchanged.");
        fxr_progress(j,FXR_CHECK,i,FXR_COUNT,fxr_files[i].path);
        if(!fxr_path(p,sizeof(p),j->root,fxr_files[i].path)||!fxr_parents(p,0))return fxr_error(j,"A runtime path is not a directory. Check the SD card.");
        int exists=fxr_exists(p);if(exists<0)return fxr_error(j,"A runtime file cannot be read or is not a regular file.");
        if(!fxr_matches(p,fxr_files[i].size,fxr_files[i].hash,j)){j->flags[i]=exists?3:1;j->changed++;}
    }
    if(fxr_cancel(j))return fxr_error(j,"Check cancelled. Runtime unchanged.");
    fxr_progress(j,FXR_CHECK,FXR_COUNT,FXR_COUNT,"");return 1;
}
static int fxr_stage(struct fxr_job *j,const char *archive){
    fxr_progress(j,FXR_VERIFY,0,FXR_COUNT,"Checking package SHA256");
    if(!fxr_matches(archive,FXR_ARCHIVE_SIZE,FXR_ARCHIVE_SHA,j))return fxr_error(j,"Package checksum failed or verification was cancelled. Nothing installed.");
    unzFile z=unzOpen64(archive);if(!z)return fxr_error(j,"Cannot open the verified runtime package.");
    int ok=0;char member[1024],out[1024];unsigned char buffer[32768];
    for(unsigned i=0;i<FXR_COUNT;i++)if(j->flags[i]&1){
        if(fxr_cancel(j)){fxr_error(j,"Repair cancelled. Runtime unchanged.");goto end;}
        fxr_progress(j,FXR_VERIFY,i,FXR_COUNT,fxr_files[i].path);
        unz_file_info64 info;
        if(!fxr_path(member,sizeof(member),"switch/pes13-fex",fxr_files[i].path)||
           unzLocateFile(z,member,1)!=UNZ_OK||unzGetCurrentFileInfo64(z,&info,NULL,0,NULL,0,NULL,0)!=UNZ_OK||
           info.uncompressed_size!=fxr_files[i].size||S_ISLNK(info.external_fa>>16)||
           !fxr_slot(out,sizeof(out),j->root,i,"new")||!fxr_parents(out,1)||fxr_exists(out)<0){fxr_error(j,"Runtime package member is invalid.");goto end;}
        if(unzOpenCurrentFile(z)!=UNZ_OK)goto end;
        FILE *f=fopen(out,"wb");int n=0,good=f!=NULL;uint64_t total=0;
        while(good&&(n=unzReadCurrentFile(z,buffer,sizeof(buffer)))>0){
            total+=n;if(total>info.uncompressed_size||fxr_cancel(j)||fwrite(buffer,1,n,f)!=(size_t)n)good=0;
        }
        if(n<0||total!=info.uncompressed_size)good=0;
        if(f){if(fflush(f)||fsync(fileno(f)))good=0;if(fclose(f))good=0;}
        if(unzCloseCurrentFile(z)!=UNZ_OK)good=0;
        if(!good||!fxr_matches(out,fxr_files[i].size,fxr_files[i].hash,j)){fxr_error(j,"Staging failed or cancelled. Check SD space; runtime unchanged.");goto end;}
    }
    ok=FXR_SYNC();
end:unzClose(z);return ok;
}
static int fxr_install(struct fxr_job *j){
    char p[1024],old[1024],next[1024],plan[1024],temp[1024],done[1024];
    if(fxr_cancel(j))return fxr_error(j,"Repair cancelled. Runtime unchanged.");
    fxr_path(plan,sizeof(plan),j->root,".runtime-fixer/plan");fxr_path(temp,sizeof(temp),j->root,".runtime-fixer/plan.tmp");fxr_path(done,sizeof(done),j->root,".runtime-fixer/done");
    if(fxr_exists(plan)!=0||fxr_exists(done)!=0)return fxr_error(j,"Finish runtime recovery before another repair.");
    for(unsigned i=0;i<FXR_COUNT;i++)if(j->flags[i]&1){
        fxr_path(p,sizeof(p),j->root,fxr_files[i].path);fxr_slot(next,sizeof(next),j->root,i,"new");fxr_slot(old,sizeof(old),j->root,i,"old");
        if(!fxr_parents(p,1)||fxr_exists(p)!=((j->flags[i]&2)?1:0)||fxr_exists(old)!=0||
           !fxr_matches(next,fxr_files[i].size,fxr_files[i].hash,j))return fxr_error(j,"Runtime changed during repair. Recheck before installing.");
    }
    if(fxr_cancel(j))return fxr_error(j,"Repair cancelled. Runtime unchanged.");
    if(!fxr_plan_write(temp,j->flags)||FXR_RENAME(temp,plan)||!FXR_SYNC())return fxr_error(j,"Could not save repair journal. Check the SD card.");
    for(unsigned i=0;i<FXR_COUNT;i++)if(j->flags[i]&1){
        fxr_progress(j,FXR_INSTALL,i,FXR_COUNT,fxr_files[i].path);
        fxr_path(p,sizeof(p),j->root,fxr_files[i].path);fxr_slot(next,sizeof(next),j->root,i,"new");fxr_slot(old,sizeof(old),j->root,i,"old");
        if(((j->flags[i]&2)&&(FXR_RENAME(p,old)||!FXR_SYNC()))||FXR_RENAME(next,p)||!FXR_SYNC()||
           !fxr_matches(p,fxr_files[i].size,fxr_files[i].hash,NULL))goto rollback;
    }
    if(FXR_RENAME(plan,done))goto rollback;
    if(!FXR_SYNC())return fxr_error(j,"Could not finish SD commit. Relaunch to recover; keep the repair folder.");
    if(!fxr_recover(j))return 0;
    return 1;
rollback:
    if(!fxr_recover(j))return 0;
    return fxr_error(j,"Installation failed; previous runtime restored. Check the SD card.");
}
#endif
