/* Exercise the actual runtime hooks with a deterministic completion timeline. */
#include <assert.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
static uint64_t tick;
static uint64_t armGetSystemTick(void) { return tick; }
static uint64_t armTicksToNs(uint64_t n) { return n; }
static unsigned int lines;
static void log_line(const char *fmt, ...)
{
    char text[1024]; va_list args;
    va_start(args,fmt); int n=vsnprintf(text,sizeof(text),fmt,args); va_end(args);
    assert(n>0 && n<(int)sizeof(text)); assert(strstr(text,"[FRAME24]")); ++lines;
}
unsigned int wine_nx_perf24_sampling_epoch;
#include "../src/runtime/pes13_perf24_runtime.h"
int main(void)
{
    pes24_report(); assert(lines==4 && !pes24_last_present);
    tick=1000000000ull; wine_nx_perf24_present();
    tick+=16000000; wine_nx_perf24_present();
    tick+=20000000; wine_nx_perf24_present();
    wine_nx_perf24_sampling_epoch=1;
    tick+=14000000; wine_nx_perf24_present();
    tick+=20000000; wine_nx_perf24_present();
    wine_nx_perf24_sampling_epoch=2;
    tick+=20000000; wine_nx_perf24_present();
    tick+=200000000; wine_nx_perf24_present();
    assert(pes24_boundaries==2 && pes24_last_present==tick);
    struct pes24_snapshot previous={0}, d=pes24_delta(&pes24_gaps[0],&previous);
    assert(d.count[0]==1 && d.count[1]==1 && d.count[5]==1);
    assert(d.total_us==236000 && d.maximum_us==200000);
    previous=(struct pes24_snapshot){0};
    d=pes24_delta(&pes24_gaps[1],&previous);
    assert(d.count[1]==1 && d.total_us==20000);
    /* A gap across an entire sampling burst is mixed even with same parity. */
    wine_nx_perf24_sampling_epoch=4;
    tick+=3000000000ull; wine_nx_perf24_present();
    assert(pes24_boundaries==3 && pes24_gaps[0].maximum_us==200000);
    wine_nx_perf24_host(500000); wine_nx_perf24_host(1000000);
    assert(pes24_host.count[0]==2 && pes24_host.total_us==1500);
    pes24_report(); assert(lines==8);
    pes24_report(); assert(lines==12);
    puts("PERF24 actual frame hooks: first frame, long gap, phase separation, skipped full burst and reports PASS");
    return 0;
}
