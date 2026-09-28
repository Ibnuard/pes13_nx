/* Exercise the shipping observer with a deterministic physical-clock model.
 * Native rendering/guest execution are not simulated by this test. */
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>

static __thread uint64_t clock_tick;
static unsigned writes;
static uint64_t armGetSystemTick(void) { return clock_tick; }
/* Test clock uses ns so exact expected samples are simple to inspect. */
static uint64_t armTicksToNs(uint64_t tick) { return tick; }
static void log_line(const char *fmt, ...)
{
    char line[1024];
    va_list args;
    va_start(args, fmt);
    int n = vsnprintf(line, sizeof(line), fmt, args);
    va_end(args);
    assert(n > 0 && n < (int)sizeof(line));
    assert(strstr(line, "[FEX3-PACE]"));
    ++writes;
}
#include "../src/runtime/fex_frame_metrics.h"
#include "../src/runtime/fex_frame_runtime.h"

static void frame(uint64_t queue, uint64_t swapchain, uint64_t us, int result)
{
    uint64_t begin = us * 1000;
    clock_tick = begin + 700000;
    wine_nx_fex_frame_note(queue, swapchain, begin, begin + 100000,
                           begin + 200000, begin + 600000, result);
    assert(clock_tick == begin + 700000); /* observation cannot wait or advance time */
}

static void *hist_writer(void *arg)
{
    struct fex_frame_hist *hist = arg;
    for (unsigned i = 0; i < 100000; ++i) fex_frame_add(hist, 16667);
    return NULL;
}

int main(void)
{
    struct fex_frame_hist previous = {0}, hist = {0};
    for (unsigned i = 0; i < FEX_FRAME_BINS - 1; ++i) {
        assert(fex_frame_bucket(fex_frame_limits_us[i]) == i);
        assert(fex_frame_bucket(fex_frame_limits_us[i] + 1) == i + 1);
    }
    frame(1, 10, 1000, 0);
    frame(1, 10, 17667, 0);
    frame(1, 10, 517667, 0); /* sub-second stall */
    frame(1, 10, 522667, 0); /* short interval after that stall */
    assert(fex_frame_ok == 4 && fex_frame_bursts == 1 && !writes);
    assert(fex_frame_stats[0].bins[1] == 1 && fex_frame_stats[0].bins[7] == 1);
    assert(fex_frame_stats[0].bins[0] == 1 && fex_frame_stats[0].peak_us == 500000);
    assert(fex_frame_stats[1].sum_us == 2800);
    assert(fex_frame_stats[2].sum_us == 400 && fex_frame_stats[3].sum_us == 1600);

    frame(1, 11, 900000, 0); /* new swapchain has no previous frame */
    frame(2, 11, 1000000, 0); /* different queue is not a same-stream gap */
    frame(2, 11, 1010000, -4); /* error breaks the history */
    frame(2, 11, 1020000, 1000001003); /* valid suboptimal */
    frame(2, 11, 1021000, 0);
    assert(fex_frame_ok == 8 && fex_frame_errors == 1 && fex_frame_bursts == 1);
    assert(fex_frame_stats[0].bins[0] == 2);
    fex_frame_report();
    assert(writes == 5);
    clock_tick += 10000000000ull;
    fex_frame_report();
    assert(writes == 10); /* idle reporting works without a new present */

    /* Reader snapshots may straddle updates; cumulative deltas must retain
     * all counts/sums once the writers have finished. */
    pthread_t a, b;
    assert(!pthread_create(&a, NULL, hist_writer, &hist));
    assert(!pthread_create(&b, NULL, hist_writer, &hist));
    uint64_t count = 0, sum = 0;
    for (unsigned i = 0; i < 1000; ++i) {
        struct fex_frame_hist d = fex_frame_delta(&hist, &previous);
        count += d.bins[1]; sum += d.sum_us;
    }
    assert(!pthread_join(a, NULL) && !pthread_join(b, NULL));
    struct fex_frame_hist d = fex_frame_delta(&hist, &previous);
    count += d.bins[1]; sum += d.sum_us;
    assert(count == 200000 && sum == 200000ull * 16667 && d.peak_us == 16667);
    puts("PASS: exact frame-gap buckets, stall/burst, queue/swapchain isolation, errors, idle reporting, 200000 concurrent samples; no hot-path writes/waits");
    return 0;
}
