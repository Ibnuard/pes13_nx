/* LGPL-2.1-or-later. Debug launch only. File writes belong to the existing
 * maintenance thread (and orderly exit), never the capture/render callbacks.
 * Bounded queue, one previous log, maximum 4 MiB per selected debug session. */
#ifndef FEXTENDO_DEBUG_FILE_H
#define FEXTENDO_DEBUG_FILE_H
#include <pthread.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>
#include "fextendo_launch_debug.h"
#define FX_DEBUG_FILE_LIMIT (4u*1024u*1024u)
static pthread_mutex_t fx_debug_file_lock=PTHREAD_MUTEX_INITIALIZER;
static FILE *fx_debug_file;
static unsigned fx_debug_file_bytes,fx_debug_file_dropped,fx_debug_file_exit_registered;
static unsigned fx_debug_file_ready;
static char fx_debug_file_batch[FX_DEBUG_PENDING_BYTES];

static void fx_debug_file_capture_stop(void){
    if(fx_debug_try()){fx_debug_file_capture=0;fx_debug_pending_size=0;fx_debug_unlock();}
}
static void fx_debug_file_close_locked(void){
    __atomic_store_n(&fx_debug_file_ready,0,__ATOMIC_RELEASE);
    if(fx_debug_file){fclose(fx_debug_file);fx_debug_file=NULL;}
    fx_debug_file_capture_stop();
}
static void fx_debug_file_flush_locked(void){
    if(!fx_debug_file){fx_debug_file_capture_stop();return;}
    if(!fx_debug_try())return;
    unsigned n=fx_debug_pending_size,dropped=__atomic_load_n(&fx_debug_dropped,__ATOMIC_RELAXED);
    memcpy(fx_debug_file_batch,fx_debug_pending,n);fx_debug_pending_size=0;
    fx_debug_unlock();
    if(!n&&dropped==fx_debug_file_dropped)return;
    char status[128];unsigned status_n=0;
    if(dropped!=fx_debug_file_dropped){
        status_n=(unsigned)snprintf(status,sizeof(status),"[LOG] dropped_messages=%u (bounded queue or contention)\n",dropped);
        fx_debug_file_dropped=dropped;
    }
    if(n+status_n>FX_DEBUG_FILE_LIMIT-128-fx_debug_file_bytes){
        static const char limit[]="[LOG] session log limit reached; file logging stopped\n";
        fwrite(limit,1,sizeof(limit)-1,fx_debug_file);fx_debug_file_close_locked();return;
    }
    if((status_n&&fwrite(status,1,status_n,fx_debug_file)!=status_n)||
       (n&&fwrite(fx_debug_file_batch,1,n,fx_debug_file)!=n)||fflush(fx_debug_file)){
        fx_debug_file_close_locked();return;
    }
    fx_debug_file_bytes+=n+status_n;
}
static __attribute__((noinline,used)) void fx_debug_file_tick(void){
    if(!wine_nx_launch_debug_active()||!__atomic_load_n(&fx_debug_file_ready,__ATOMIC_ACQUIRE))return;
    int saved=errno;
    if(!pthread_mutex_trylock(&fx_debug_file_lock)){
        fx_debug_file_flush_locked();pthread_mutex_unlock(&fx_debug_file_lock);
    }
    errno=saved;
}
static void fx_debug_file_exit(void){
    if(pthread_mutex_trylock(&fx_debug_file_lock))return;
    fx_debug_file_flush_locked();fx_debug_file_close_locked();
    pthread_mutex_unlock(&fx_debug_file_lock);
}
static void fx_debug_file_begin(int enabled){
    pthread_mutex_lock(&fx_debug_file_lock);
    fx_debug_file_flush_locked();fx_debug_file_close_locked();
    fx_launch_debug_begin(enabled);
    pthread_mutex_unlock(&fx_debug_file_lock);
}
static __attribute__((noinline,used)) int fx_debug_file_prepare(const char *root){
    int ok=1;char path[768],previous[768];struct stat st;
    pthread_mutex_lock(&fx_debug_file_lock);
    __atomic_store_n(&fx_debug_file_ready,0,__ATOMIC_RELEASE);
    if(fx_debug_file){fx_debug_file_flush_locked();fclose(fx_debug_file);fx_debug_file=NULL;}
    if(!wine_nx_launch_debug_active()){
        fx_debug_file_capture_stop();pthread_mutex_unlock(&fx_debug_file_lock);return 1;
    }
    if(snprintf(path,sizeof(path),"%s/fex-runtime.log",root)>=(int)sizeof(path)||
       snprintf(previous,sizeof(previous),"%s/fex-runtime.previous.log",root)>=(int)sizeof(previous)){ok=0;goto done;}
    if(!stat(path,&st)){
        if(!S_ISREG(st.st_mode)){ok=0;goto done;}
        if(!stat(previous,&st)){
            if(!S_ISREG(st.st_mode)||unlink(previous)){ok=0;goto done;}
        }else if(errno!=ENOENT){ok=0;goto done;}
        if(rename(path,previous)){ok=0;goto done;}
    }else if(errno!=ENOENT){ok=0;goto done;}
    fx_debug_file=fopen(path,"wb");
    if(!fx_debug_file){ok=0;goto done;}
    /* Producers already queue batches. No separate stdio buffer is needed. */
    setvbuf(fx_debug_file,NULL,_IONBF,0);
    fx_debug_file_bytes=fx_debug_file_dropped=0;
    __atomic_store_n(&fx_debug_file_ready,1,__ATOMIC_RELEASE);
    if(!fx_debug_file_exit_registered){atexit(fx_debug_file_exit);fx_debug_file_exit_registered=1;}
done:
    if(!ok)fx_debug_file_capture_stop();
    pthread_mutex_unlock(&fx_debug_file_lock);
    fx_launch_debug_log(ok?"[LOG] fex-runtime.log enabled; previous run kept; crash.log armed separately":
        "[LOG] file logging unavailable; check SD space/access; startup console still available");
    return ok;
}
#endif
