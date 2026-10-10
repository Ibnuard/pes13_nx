#include <assert.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
static int enabled,verify_unlocked=1;
static unsigned reports;
static char last[256],summary[256];
static int wine_nx_launch_debug_active(void){return enabled;}
static pthread_mutex_t horizon_server_objects_mutex=PTHREAD_MUTEX_INITIALIZER;
struct fxap_pipe {pthread_mutex_t lock;unsigned capacity,used,read_open,write_open;};
struct horizon_server_object {struct fxap_pipe *anon_pipe;unsigned anon_writer,anon_io_active,refs;};
struct horizon_server_handle_entry {unsigned handle;struct horizon_server_object *object;struct horizon_server_handle_entry *next;};
static struct horizon_server_handle_entry *horizon_server_handles;
static void horizon_trace(const char *format,...)
{
    /* A logging callback must never run with the registry still locked. */
    if(verify_unlocked){
        assert(!pthread_mutex_trylock(&horizon_server_objects_mutex));
        pthread_mutex_unlock(&horizon_server_objects_mutex);
    }
    va_list args;va_start(args,format);vsnprintf(last,sizeof(last),format,args);va_end(args);reports++;
    if(strstr(last,"[ASSET-PIPES]"))strcpy(summary,last);
}
#include "horizon_asset_probe.h"
int main(void)
{
    struct fxap_pipe pipe={PTHREAD_MUTEX_INITIALIZER,2101740,1050870,1,1};
    struct horizon_server_object object={&pipe,0,0,1};
    struct horizon_server_handle_entry entry={0xa4ec,&object,NULL};
    horizon_server_handles=&entry;
    wine_nx_asset_pipe_report();assert(!reports);
    enabled=1;wine_nx_asset_pipe_report();assert(reports==2);
    assert(strstr(last,"handle=a4ec")&&strstr(last,"queued=1050870"));
    assert(pipe.used==1050870&&pipe.read_open&&pipe.write_open);
    pthread_mutex_lock(&pipe.lock);wine_nx_asset_pipe_report();pthread_mutex_unlock(&pipe.lock);
    assert(strstr(last,"busy=1"));
    pthread_mutex_lock(&horizon_server_objects_mutex);verify_unlocked=0;wine_nx_asset_pipe_report();
    assert(strstr(last,"object registry busy"));
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    verify_unlocked=1;
    struct horizon_server_handle_entry entries[2050];
    for(unsigned i=0;i<2050;i++)entries[i]=(struct horizon_server_handle_entry){i,&object,i+1<2050?&entries[i+1]:NULL};
    horizon_server_handles=entries;wine_nx_asset_pipe_report();
    assert(strstr(summary,"scanned=2048 shown=8 busy=0 omitted=2040 scan_truncated=1"));
    assert(pipe.used==1050870&&pipe.read_open&&pipe.write_open);
    puts("PASS quiet/ready/busy pipe snapshots; queued bytes and ownership unchanged");
}
