/* LGPL-2.1-or-later. Network resources live only during a manual repair. */
#ifndef FEXTENDO_RUNTIME_DOWNLOAD_H
#define FEXTENDO_RUNTIME_DOWNLOAD_H
#include <curl/curl.h>
#include <sys/statvfs.h>
#include "fextendo_runtime_fixer.h"
struct fxr_transfer {struct fxr_job *job;FILE *file;uint64_t received;};
static size_t fxr_receive(char *ptr,size_t size,size_t count,void *data){
    struct fxr_transfer *t=data;
    if(size&&count>SIZE_MAX/size)return 0;
    size_t bytes=size*count;
    if(fxr_cancel(t->job)||bytes>FXR_ARCHIVE_SIZE-t->received)return 0;
    size_t wrote=fwrite(ptr,1,bytes,t->file);t->received+=wrote;
    fxr_progress(t->job,FXR_DOWNLOAD,t->received,FXR_ARCHIVE_SIZE,"Runtime package from GitHub");return wrote;
}
static int fxr_transfer_progress(void *data,curl_off_t total,curl_off_t now,curl_off_t utotal,curl_off_t unow){
    (void)total;(void)now;(void)utotal;(void)unow;return fxr_cancel(((struct fxr_transfer *)data)->job);
}
static int fxr_download(struct fxr_job *j,const char *path){
    int ok=0,global=0;CURL *curl=NULL;FILE *f=NULL;long status=0;
    char error[CURL_ERROR_SIZE]={0};CURLcode result=CURLE_FAILED_INIT;
#ifdef __SWITCH__
    Result rc=socketInitializeDefault();if(R_FAILED(rc))return fxr_error(j,"Network initialization failed. Connect Wi-Fi and retry.");
#endif
    if(curl_global_init(CURL_GLOBAL_DEFAULT)!=CURLE_OK)goto end;
    global=1;curl=curl_easy_init();if(!curl)goto end;
    if(!fxr_parents(path,1)||fxr_exists(path)<0)goto end;
    f=fopen(path,"wb");if(!f)goto end;
    struct fxr_transfer transfer={j,f,0};
#define FXR_CURL(option,value) do{result=curl_easy_setopt(curl,option,value);if(result!=CURLE_OK)goto end;}while(0)
    FXR_CURL(CURLOPT_URL,FXR_URL);
    FXR_CURL(CURLOPT_PROTOCOLS,CURLPROTO_HTTPS);
    FXR_CURL(CURLOPT_REDIR_PROTOCOLS,CURLPROTO_HTTPS);
    FXR_CURL(CURLOPT_FOLLOWLOCATION,1L);FXR_CURL(CURLOPT_MAXREDIRS,4L);
    FXR_CURL(CURLOPT_SSL_VERIFYPEER,1L);FXR_CURL(CURLOPT_SSL_VERIFYHOST,2L);
    FXR_CURL(CURLOPT_SSLVERSION,CURL_SSLVERSION_TLSv1_2);
    FXR_CURL(CURLOPT_FAILONERROR,1L);FXR_CURL(CURLOPT_NOSIGNAL,1L);
    FXR_CURL(CURLOPT_CONNECTTIMEOUT,20L);FXR_CURL(CURLOPT_TIMEOUT,900L);
    FXR_CURL(CURLOPT_LOW_SPEED_LIMIT,1024L);FXR_CURL(CURLOPT_LOW_SPEED_TIME,30L);
    FXR_CURL(CURLOPT_USERAGENT,"FEXTendo-Runtime-Fixer/1");
    FXR_CURL(CURLOPT_ERRORBUFFER,error);FXR_CURL(CURLOPT_WRITEFUNCTION,fxr_receive);
    FXR_CURL(CURLOPT_WRITEDATA,&transfer);FXR_CURL(CURLOPT_NOPROGRESS,0L);
    FXR_CURL(CURLOPT_XFERINFOFUNCTION,fxr_transfer_progress);FXR_CURL(CURLOPT_XFERINFODATA,&transfer);
    result=curl_easy_perform(curl);curl_easy_getinfo(curl,CURLINFO_RESPONSE_CODE,&status);
    ok=result==CURLE_OK&&status==200&&transfer.received==FXR_ARCHIVE_SIZE&&!ferror(f)&&!fflush(f)&&!fsync(fileno(f));
#undef FXR_CURL
end:
    if(f&&fclose(f))ok=0;
    if(curl)curl_easy_cleanup(curl);
    if(global)curl_global_cleanup();
#ifdef __SWITCH__
    socketExit();
#endif
    if(!ok){
        fxr_remove(path);
        if(fxr_cancel(j))return fxr_error(j,"Download cancelled. Runtime unchanged.");
        snprintf(j->error,sizeof(j->error),"Download failed (HTTP %ld, curl %d). Check Wi-Fi, SD space and system date; runtime unchanged.",status,(int)result);
    }
    return ok;
}
static int fxr_repair(struct fxr_job *j){
    if(!j->changed)return 1;
    struct statvfs space;uint64_t required=FXR_ARCHIVE_SIZE+8*1024*1024;
    for(unsigned i=0;i<FXR_COUNT;i++)if(j->flags[i]&1)required+=fxr_files[i].size;
    if(statvfs(j->root,&space)||(uint64_t)space.f_bavail*space.f_frsize<required)return fxr_error(j,"Not enough free SD space to download and stage the runtime safely.");
    char archive[1024];if(!fxr_path(archive,sizeof(archive),j->root,".runtime-fixer/package.part")||!fxr_parents(archive,1)||!fxr_clean(j->root))return fxr_error(j,"Could not prepare repair storage.");
    int ok=fxr_download(j,archive)&&fxr_stage(j,archive)&&fxr_install(j);
    fxr_remove(archive);
    /* Never discard backups after a failed recovery. A subsequent launch owns it. */
    char plan[1024],done[1024];fxr_path(plan,sizeof(plan),j->root,".runtime-fixer/plan");fxr_path(done,sizeof(done),j->root,".runtime-fixer/done");
    if(fxr_exists(plan)==0&&fxr_exists(done)==0)fxr_clean(j->root);
    if(!ok&&!j->error[0])fxr_error(j,"Runtime repair failed. Check the SD card and retry.");
    return ok;
}
#endif
