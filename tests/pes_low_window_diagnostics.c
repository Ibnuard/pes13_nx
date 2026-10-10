#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
static int debug,game,frames,pipelines,warm,writes;
static uint64_t tick;
unsigned int wine_nx_sd_reads,wine_nx_sd_hits;
unsigned long long wine_nx_sd_read_ns;
static int wine_nx_launch_debug_active(void){return debug;}
static uint64_t armGetSystemTick(void){return tick;}
static uint64_t armTicksToNs(uint64_t t){return t;}
static void fex_game_timing_report(void){game++;}
static void fex_frame_report(void){frames++;}
static void fex_pipeline_report(void){pipelines++;}
static void fex_warm_report(void){warm++;}
static char last[512];
static void log_line(const char *fmt,...){
    va_list ap;va_start(ap,fmt);vsnprintf(last,sizeof(last),fmt,ap);va_end(ap);writes++;
}
#include "../src/runtime/pes_low_window_diagnostics.h"
int main(void){
    for(unsigned i=1;i<=100;i++)fx_low_window_diagnostics(i);
    assert(!(game||frames||pipelines||warm||writes));
    debug=1;tick=10000000000ull;wine_nx_sd_reads=100;wine_nx_sd_hits=200;wine_nx_sd_read_ns=1234000;
    for(unsigned i=1;i<=50;i++)fx_low_window_diagnostics(i);
    assert(game==2&&frames==1&&pipelines==1&&warm==1&&writes==1);
    assert(strstr(last,"reads=100 cache_hits=200 fs_read_us=1234"));
    tick+=10000000000ull;wine_nx_sd_reads+=7;wine_nx_sd_hits+=9;wine_nx_sd_read_ns+=500000;
    fx_low_window_diagnostics(100);
    assert(strstr(last,"window_ms=10000 reads=7 cache_hits=9 fs_read_us=500"));
    debug=0;fx_low_window_diagnostics(150);assert(game==3&&writes==2);
    puts("PASS: normal launch performs no diagnostic work; Debug cadence and counter deltas correct.");
}
