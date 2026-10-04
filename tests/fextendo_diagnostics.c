/* Exercise opt-in and bounded worker logging, with modeled Horizon counters. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <malloc.h>
#define RUNTIME_DIR "fixture"
#define CUR_PROCESS_HANDLE 1
#define InfoType_UsedMemorySize 1
#define InfoType_TotalMemorySize 2
#define R_SUCCEEDED(x) ((x)==0)
typedef int Result;
static struct {int selected,renderer;} fx_ui_view={3,1};
static uint64_t fex_frame_last,fex_frame_ok,fex_frame_errors,now;
static int enabled,reads,opens,closes,moves,queries,lines;
static uint64_t armGetSystemTick(void){return now;}
static uint64_t armTicksToNs(uint64_t ticks){return ticks*1000000;}
#ifdef FX_TRANSITION_TRACE
static unsigned threadGetCurHandle(void){return 9;}
char *fake_heap_start=(char *)0x100000000ULL,*fake_heap_end=(char *)0x180000000ULL;
#include "../src/runtime/fextendo_transition_trace.h"
static int memory_lines,event_lines,escaped_lines,inflight_lines,failure_lines,alloc_lines;
#ifdef FX_SCRATCH_RESERVE
#if FX_SCRATCH_RESERVE_VERSION == 3
#define EXPECT_SCRATCH_TAG "SCRATCH_V3"
#else
#define EXPECT_SCRATCH_TAG "SCRATCH_V2"
#endif
static int scratch_reads,scratch_lines;
void pes13_fex_scratch_snapshot(uint64_t out[16]){
    static const uint64_t values[16]={33554432,16777216,1,10,3,1,33554432,9,0,16777216,41943040,41943040,4,6,0,0};
    memcpy(out,values,sizeof(values));scratch_reads++;
}
#endif
#endif
#ifdef FX_PAGE_STORE
static unsigned page_reads,page_lines;
void wine_nx_page_store_snapshot(uint64_t out[8]) {
    static const uint64_t values[8]={2,22020096,5242880,5,0,0,22020096,1};
    memcpy(out,values,sizeof(values));page_reads++;
}
#endif
#ifdef FX_LIVE_TRACE
#ifdef FX_SCRATCH_PAGES
static unsigned sp_reads,sp_lines;
void pes13_fex_scratch_pages_snapshot(uint64_t out[15]){
    static const uint64_t values[15]={1,1,0,16777216,16777216,1,16,0,0,0,0,0,0,16777216,0};
    memcpy(out,values,sizeof(values));sp_reads++;
}
#endif
#ifdef FX_THREAD_STACK_RESERVE
static unsigned stack_reads,stack_lines;
static void fx_thread_stack_snapshot(uint64_t out[15]){
    static const uint64_t values[15]={8,1052672,1,2,3,2,0,0,0,98,0,0,0,0,3};
    memcpy(out,values,sizeof(values));stack_reads++;
}
#endif
#include "../src/runtime/fextendo_live_trace.h"
static unsigned live_reads,live_lines,thread_lines;
void wine_nx_live_threads_snapshot(struct fx_live_snapshot *out){
    assert(fex_frame_ok&&now-fex_frame_last==16);live_reads++;
    memset(out,0,sizeof(*out));out->count=1;out->context_supported=1;out->elapsed_us=123;
    out->rows[0]=(struct fx_live_thread){.handle=0xab,.tid=4,.kind='w',.ticks=1234,.pc=0x11223344};
}
#endif
static int fx_keyboard_input_blocked(void){return 0;}
static size_t fx_read(const char *p,void *b,size_t n){
    assert(!strcmp(p,RUNTIME_DIR "/launcher/diagnostics.txt")&&n==2);reads++;
    if(enabled){memcpy(b,"1\n",2);return 2;}return 0;
}
static Result svcGetInfo(uint64_t *out,int type,int handle,int index){
    assert(handle==1&&!index);queries++;*out=type*1024;return 0;
}
static int diag_unlink(const char *p){assert(strstr(p,"transition.previous.log"));moves++;return 0;}
static int diag_rename(const char *a,const char *b){assert(strstr(a,"transition.log")&&strstr(b,"transition.previous.log"));moves++;return 0;}
static FILE *diag_open(const char *p,const char *mode){assert(strstr(p,"transition.log")&&!strcmp(mode,"wb"));opens++;return tmpfile();}
static int diag_close(FILE *f){
    char row[4096];rewind(f);while(fgets(row,sizeof(row),f)){
        lines++;
#ifdef FX_SCRATCH_PAGES
        sp_lines+=!strcmp(row,"SCRATCH_PAGES_V1 attempts=1 recovered=1 failed=0 held_bytes=16777216 peak_bytes=16777216 held_slots=1 pieces=16 returned=0 map_failed=0 unmap_failed=0 quarantined=0 invalid_release=0 last_result=0 last_request=16777216 budget_refused=0\n");
#endif
#ifdef FX_THREAD_STACK_RESERVE
        stack_lines+=!strcmp(row,"THREAD_STACK_V1 capacity=8 slot_bytes=1052672 used=1 peak=2 recovered=3 returned=2 exhausted=0 quarantined=0 invalid_release=0 calls=98 failed=0 last_result=0 last_stack=0 init_failed=0 alloc_failed=3\n");
#endif
#ifdef FX_PAGE_STORE
        page_lines+=!strcmp(row,"PAGES_V1 recovered=2 recovered_bytes=22020096 live_bytes=5242880 pieces=5 failed=0 rollback_failed=0 peak_bytes=22020096 released=1\n");
#endif
#ifdef FX_TRANSITION_TRACE
        memory_lines+=!strncmp(row,"MEM ",4);
        event_lines+=!strncmp(row,"EVENT kind=1 code=deadbeef",26);
        escaped_lines+=!strcmp(row,"TEXT test\\x0aEVENT forged\\x00\\x5c\n");
        inflight_lines+=!strncmp(row,"INFLIGHT name=present ",22);
        failure_lines+=strstr(row,"[FEX2-HEAP] STOP scratch\\x0aforged")!=NULL;
        alloc_lines+=!strcmp(row,"ALLOC_SITE kind=4 thread=9 age_ms=1800 size=5242880 alignment=4096 caller=12345678 errno=12\n");
#ifdef FX_SCRATCH_RESERVE
        scratch_lines+=!strcmp(row,EXPECT_SCRATCH_TAG " capacity=33554432 used=16777216 live=1 hits=10 fallback=3 failed=1 peak_used=33554432 returned=9 init_failed=0 largest_free=16777216 max_request=41943040 last_failed=41943040 hits_8=4 hits_16=6 hits_larger=0 invalid_release=0\n");
#endif
#endif
#ifdef FX_LIVE_TRACE
        live_lines+=!strncmp(row,"LIVE_V1 elapsed_ms=",19);
        thread_lines+=strstr(row,"THREAD handle=ab tid=4 kind=119 ticks=1234")!=NULL;
#endif
    }
    closes++;return fclose(f);
}
#define unlink diag_unlink
#define rename diag_rename
#define fopen diag_open
#define fclose diag_close
#include "../src/runtime/fextendo_diagnostics.h"
int main(int argc,char **argv){
    assert(argc==2);enabled=atoi(argv[1]);
    for(unsigned tick=1;tick<=100;tick++)fx_diagnostics_tick(tick);
    assert(!reads&&!opens);
    for(unsigned tick=1;tick<=12000;tick++){
        now=tick*200;fex_frame_last=now-16;fex_frame_ok+=12;
        fx_diagnostics_tick(tick);
#ifdef FX_TRANSITION_TRACE
        if(tick==1){
            wine_nx_transition_event(1,0xdeadbeef,0,0);
            wine_nx_transition_text("test\nEVENT forged\0\\",19);
            wine_nx_transition_begin(1,123);
            wine_nx_transition_failure_line("[FEX2-HEAP] STOP scratch\nforged");
            wine_nx_transition_alloc_site(4,5242880,4096,0x12345678,12);
        }
#endif
    }
    assert(reads==1);
    if(enabled){
        assert(opens==1&&closes==1&&moves==2&&queries==1200);
#ifdef FX_TRANSITION_TRACE
        assert(memory_lines==600&&event_lines==1&&escaped_lines==1&&inflight_lines==600);
        assert(failure_lines==1&&alloc_lines==1);
        assert(!fx_tr_on());
#else
        assert(lines==602);
#endif
    }
    else assert(!opens&&!closes&&!moves&&!queries&&!lines);
#ifdef FX_SCRATCH_RESERVE
    assert(scratch_reads==(enabled?600:0)&&scratch_lines==scratch_reads);
#endif
#ifdef FX_PAGE_STORE
    assert(page_reads==(enabled?600:0)&&page_lines==page_reads);
#endif
#ifdef FX_THREAD_STACK_RESERVE
    assert(stack_reads==(enabled?600:0)&&stack_lines==stack_reads);
#endif
#ifdef FX_SCRATCH_PAGES
    assert(sp_reads==(enabled?600:0)&&sp_lines==sp_reads);
#endif
#ifdef FX_LIVE_TRACE
    assert(live_reads==(enabled?200:0)&&live_lines==live_reads&&thread_lines==live_reads);
#endif
    puts(enabled?"PASS: diagnostics stop at 600 two-second samples":"PASS: disabled diagnostics perform one config read and no writes");
}
