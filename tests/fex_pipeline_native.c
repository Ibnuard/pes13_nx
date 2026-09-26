/* Deterministic observer test. Driver calls/physical scheduling are not modeled. */
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
    char line[1024];
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(line, sizeof(line), fmt, ap);
    va_end(ap);
    assert(n > 0 && n < (int)sizeof(line) && strstr(line, "[FEX3-PIPE]"));
    ++writes;
}
#include "../src/runtime/fex_frame_metrics.h"
#include "../src/runtime/fex_pipeline_runtime.h"
int main(void)
{
    uint64_t begin = 1000000;
    tick = begin + 100000;
    wine_nx_fex_pipeline_note(0, begin, 0);
    tick = begin + 500000000;
    wine_nx_fex_pipeline_note(2, begin, 2); /* timeout is measured, not discarded */
    tick = begin + 7000000;
    wine_nx_fex_pipeline_note(3, begin, -4); /* device lost return retained */
    assert(fex_pipeline_stats[0].sum_us == 100 && fex_pipeline_stats[0].bins[0] == 1);
    assert(fex_pipeline_stats[2].sum_us == 500000 && fex_pipeline_stats[2].bins[7] == 1);
    assert(fex_pipeline_stats[3].sum_us == 7000 && fex_pipeline_errors[3] == 1);
    assert(fex_pipeline_timeouts[2] == 1 && !writes && tick == begin + 7000000);
    wine_nx_fex_pipeline_note(5, begin, 0);
    tick = begin - 1;
    wine_nx_fex_pipeline_note(1, begin, 0);
    assert(fex_pipeline_invalid == 2 && !fex_pipeline_stats[1].sum_us);

    wine_nx_fex_shared_clock_note(100000000); /* 100 ns units */
    wine_nx_fex_shared_clock_note(100010000); /* 1 ms update */
    wine_nx_fex_shared_clock_note(105010000); /* 500 ms missed updates */
    wine_nx_fex_shared_clock_note(105010000); /* same tick */
    assert(fex_pipeline_stats[4].sum_us == 501000 && fex_pipeline_stats[4].peak_us == 500000);
    assert(fex_pipeline_stats[4].bins[0] == 2 && fex_pipeline_stats[4].bins[7] == 1);
    wine_nx_fex_shared_clock_note(105000000); /* invalid clock progression */
    assert(fex_pipeline_invalid == 3);
    fex_pipeline_report();
    fex_pipeline_report(); /* idle reports do not alter counters */
    assert(writes == 12 && fex_pipeline_timeouts[2] == 1);
    puts("PASS: stage isolation; long acquire/wait timeout/error accounting; shared-clock units/gap; invalid/reversed time; idle reporting; no waits or hot-path writes");
    return 0;
}
