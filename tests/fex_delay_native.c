#include <assert.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static uint64_t tick;
static unsigned writes;
static uint64_t armGetSystemTick(void) { return tick; }
static uint64_t armTicksToNs(uint64_t value) { return value; }
static void log_line(const char *fmt, ...)
{
    char line[1024]; va_list ap;
    va_start(ap,fmt); int n=vsnprintf(line,sizeof(line),fmt,ap); va_end(ap);
    assert(n>0 && n<(int)sizeof(line)); ++writes;
}
void wine_nx_fex_sync_snapshot(uint64_t out[7]) { memset(out,0,7*sizeof(*out)); }
#include "../src/runtime/fex_sync_runtime.h"
int main(void)
{
    tick=1000000; wine_nx_fex_delay_note(4,0,1,0,0,0); /* 1ms yield */
    assert(fex_delay_rows[1].yields==1 && fex_delay_rows[1].yield_us==1000);
    tick=7000000; wine_nx_fex_delay_note(4,0,1,-50000,0,0); /* 5ms requested, 7ms elapsed */
    assert(fex_delay_rows[1].requested_us==5000 && fex_delay_rows[1].excess_us==2000);
    tick=55000000; wine_nx_fex_delay_note(4,0,1,-170000,0,0);
    assert(fex_delay_rows[1].actual_us==62000 && fex_delay_rows[1].excess_peak_us==38000);
    assert(fex_delay_rows[1].late20==1);
    wine_nx_fex_delay_note(4,1,1,-170000,0,0); /* alertable: do not infer oversleep */
    wine_nx_fex_delay_note(4,0,1,170000,0,0); /* absolute deadline */
    wine_nx_fex_delay_note(4,0,0,0,0,0); /* nullable */
    wine_nx_fex_delay_note(4,0,1,-170000,0,-1); /* error */
    assert(fex_delay_rows[1].other==4 && !writes);
    /* Hash collision and full table stay bounded; signed negation is avoided. */
    for (unsigned i=1;i<=FEX_DELAY_ROWS;++i) wine_nx_fex_delay_note(4+i*256,0,1,INT64_MIN,0,0);
    assert(fex_delay_overflow==1 && fex_delay_rows[1].tid==4);
    fex_sync_report(); assert(writes==66); /* sync, 64 rows, overflow */
    fex_sync_report(); assert(writes==67); /* idle: sync only */
    puts("PASS delay observer: per-thread yield/sleep, 100ns units, overshoot, errors/alertable/absolute, bounded collisions, no hot writes");
}
