#include <assert.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
static unsigned enabled,clock_calls,finished;
static _Thread_local unsigned test_thread=1;
static uint64_t test_clock(void){return __atomic_add_fetch(&clock_calls,1,__ATOMIC_RELAXED);}
static int wine_nx_launch_debug_active(void){return __atomic_load_n(&enabled,__ATOMIC_RELAXED);}
#define FX_WAIT_THREAD() test_thread
#define FX_WAIT_NOW() test_clock()
#define FX_WAIT_NO_REPORT
#include "fextendo_wait_probe.h"

static void reset(void){
    memset(fx_wait_rows,0,sizeof(fx_wait_rows));memset(fx_wait_started,0,sizeof(fx_wait_started));
    memset(fx_wait_finished,0,sizeof(fx_wait_finished));fx_wait_dropped=fx_wait_cursor=clock_calls=0;
    memset(fx_wait_errors,0,sizeof(fx_wait_errors));fx_wait_error_total=fx_wait_error_dropped=0;
}
static void *worker(void *arg){
    test_thread=(unsigned)(uintptr_t)arg;
    for(unsigned i=0;i<15000;i++){
        uint64_t a=wine_nx_wait_probe_begin(i%3,test_thread^0x100,test_thread,~(uint64_t)test_thread);
        uint64_t b=wine_nx_wait_probe_begin((i+1)%3,test_thread^0x100,test_thread,~(uint64_t)test_thread);
        wine_nx_wait_probe_end(b,0xc0000001);wine_nx_wait_probe_end(a,0);
    }
    __atomic_add_fetch(&finished,1,__ATOMIC_RELEASE);return NULL;
}
int main(void){
    uint64_t tokens[FX_WAIT_SLOTS];struct fx_wait_row row;
    errno=123;assert(!wine_nx_wait_probe_begin(0,1,UINT64_MAX,UINT64_MAX));
    wine_nx_wait_probe_end(0,0);assert(clock_calls==0&&errno==123);
    enabled=1;
    for(unsigned i=0;i<FX_WAIT_SLOTS;i++){tokens[i]=wine_nx_wait_probe_begin(i%3,i,i,~(uint64_t)i);assert(tokens[i]);}
    assert(!wine_nx_wait_probe_begin(1,9,0,0)&&fx_wait_dropped==1);
    for(unsigned i=0;i<FX_WAIT_SLOTS;i++)assert(fx_wait_read(i,&row)&&row.state&1);
    for(unsigned i=0;i<FX_WAIT_SLOTS;i++)wine_nx_wait_probe_end(tokens[i],i);
    uint64_t fresh=wine_nx_wait_probe_begin(2,9,123,456);unsigned index=(unsigned)fresh-1;
    wine_nx_wait_probe_end(tokens[index],0xdeadbeef);assert(fx_wait_read(index,&row)&&row.state&1&&row.arg0==123);
    wine_nx_wait_probe_end(fresh,0xc0000005);assert(fx_wait_read(index,&row)&&!(row.state&3)&&row.result==0xc0000005);
    wine_nx_wait_probe_end(fresh,0);assert(fx_wait_finished[2]==43);
    assert(!wine_nx_wait_probe_begin(3,0,0,0));
    fx_wait_rows[0].state=0xfffffffc;fx_wait_cursor=0;
    fresh=wine_nx_wait_probe_begin(0,1,0,0);assert((fresh>>32)==4);wine_nx_wait_probe_end(fresh,0);
    reset();
    /* A one-time read failure survives many successful frames/audio calls. */
    fresh=wine_nx_wait_probe_begin(0,0x111,0xa4ec,456);wine_nx_wait_probe_end(fresh,0xc000000d);
    for(unsigned i=0;i<4096;i++){
        fresh=wine_nx_wait_probe_begin(i%3,1,i,0);wine_nx_wait_probe_end(fresh,0);
    }
    struct fx_wait_error error;
    assert(fx_wait_error_total==1&&fx_wait_error_read(0,&error));
    assert(error.row.arg0==0xa4ec&&error.row.result==0xc000000d&&error.row.code==0x111);
    fresh=wine_nx_wait_probe_begin(1,1,0,0);wine_nx_wait_probe_end(fresh,0xc00000cb);
    fresh=wine_nx_wait_probe_begin(0,1,0,0);wine_nx_wait_probe_end(fresh,0x102);
    assert(fx_wait_error_total==1); /* internal routing and timeouts are excluded */
    reset();pthread_t threads[8];
    for(unsigned i=0;i<8;i++)assert(!pthread_create(&threads[i],NULL,worker,(void *)(uintptr_t)(i+1)));
    while(__atomic_load_n(&finished,__ATOMIC_ACQUIRE)!=8){
        for(unsigned i=0;i<FX_WAIT_SLOTS;i++)if(fx_wait_read(i,&row)){
            assert(row.kind<3&&row.thread>=1&&row.thread<=8);
            assert(row.code==(row.thread^0x100)&&row.arg0==row.thread&&row.arg1==~(uint64_t)row.thread);
        }
        for(unsigned i=0;i<FX_WAIT_ERRORS;i++)if(fx_wait_error_read(i,&error)){
            assert(error.row.kind==0&&error.row.result==0xc0000001&&error.serial);
            assert(error.row.thread>=1&&error.row.thread<=8);
            assert(error.row.code==(error.row.thread^0x100));
            assert(error.row.arg0==error.row.thread&&error.row.arg1==~(uint64_t)error.row.thread);
        }
    }
    for(unsigned i=0;i<8;i++)pthread_join(threads[i],NULL);
    for(unsigned i=0;i<FX_WAIT_SLOTS;i++)assert(!(fx_wait_rows[i].state&3));
    for(unsigned i=0;i<3;i++)assert(fx_wait_started[i]==fx_wait_finished[i]);
    assert(fx_wait_started[0]+fx_wait_started[1]+fx_wait_started[2]+fx_wait_dropped==240000);
    assert(fx_wait_error_total>FX_WAIT_ERRORS);
    puts("PASS quiet, capacity, stale tokens, nesting, sticky NT failures, error-ring overflow, wrap, 240000 concurrent calls and snapshots");
}
