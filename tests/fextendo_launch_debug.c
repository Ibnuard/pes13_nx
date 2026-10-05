#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include <stdint.h>
static uint64_t now_ms=1000;
#define FX_LAUNCH_DEBUG_NOW() now_ms
#include "../src/runtime/fextendo_launch_debug.h"
static void *writer(void *unused){
    (void)unused;for(int i=0;i<10000;i++)wine_nx_launch_debug_write("parallel Wine output\n",21);return NULL;
}
int main(void){
    struct fx_debug_snapshot out={0};
    fx_launch_debug_begin(0);wine_nx_launch_debug_write((void *)1,SIZE_MAX);
    fx_launch_debug_log((void *)1);assert(!wine_nx_launch_debug_flags((void *)1));
    assert(fx_launch_debug_snapshot(&out)&&!out.count);
    fx_launch_debug_begin(1);now_ms=2250;errno=EIO;
    wine_nx_launch_debug_write("load ",5);wine_nx_launch_debug_write("ntdll\n",6);
    assert(errno==EIO);assert(fx_launch_debug_snapshot(&out));
    assert(out.count==1&&!strcmp(out.lines[0],"[1.250] load ntdll"));
    assert(out.elapsed_ms==1250&&wine_nx_launch_debug_flags("loaddll")==14);
    assert(wine_nx_launch_debug_flags("d3d")==6);
    for(unsigned i=0;i<100;i++)fx_launch_debug_log("row=%u",i);
    assert(fx_launch_debug_snapshot(&out)&&out.count==64);
    assert(strstr(out.lines[0],"row=36")&&strstr(out.lines[63],"row=99"));
    char huge[5000];memset(huge,'x',sizeof(huge));wine_nx_launch_debug_write(huge,sizeof(huge));
    assert(fx_launch_debug_snapshot(&out)&&out.dropped==1);
    fx_debug_lock=1;wine_nx_launch_debug_write("must not wait",13);
    assert(!fx_launch_debug_snapshot(&out));fx_debug_lock=0;
    assert(fx_launch_debug_snapshot(&out)&&out.dropped==2);
    pthread_t a,b;assert(!pthread_create(&a,NULL,writer,NULL));assert(!pthread_create(&b,NULL,writer,NULL));
    for(int i=0;i<10000;i++)if(fx_launch_debug_snapshot(&out)){
        assert(out.count<=64);for(unsigned j=0;j<out.count;j++)assert(strlen(out.lines[j])<=FX_DEBUG_COLS);
    }
    pthread_join(a,NULL);pthread_join(b,NULL);
    fx_launch_debug_begin(0);assert(!wine_nx_launch_debug_active());
    fx_launch_debug_begin(1);assert(fx_launch_debug_snapshot(&out)&&!out.count&&!out.dropped);
    puts("Screen-only ring: quiet path, streaming, wrap, bounds, contention, concurrent snapshots and reset passed.");
}
