/* Read-only game probe and batched logger: protection failures, clock histories,
 * identity mismatches, object replacement and thread-local flush isolation. */
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../src/runtime/fex_game_timing.h"
#include "../src/runtime/fex_log_policy.h"

static unsigned char memory[0x2100000];
static uint32_t fail_address, replace_object;
static unsigned pointer_reads, writes;
static uint64_t clock_tick;
static char output[4096];
static uint64_t armGetSystemTick(void) { return clock_tick; }
static uint64_t armTicksToNs(uint64_t t) { return t; }
static void log_line(const char *fmt, ...)
{
    size_t n = strlen(output);
    va_list args;
    va_start(args, fmt);
    int used = vsnprintf(output + n, sizeof(output) - n, fmt, args);
    va_end(args);
    assert(used > 0 && used < (int)(sizeof(output) - n));
    ++writes;
}
int wine_nx_fex_timing_read(uint32_t a, void *out, size_t n)
{
    if (a == fail_address || a > sizeof(memory) || n > sizeof(memory) - a) return 0;
    if (a == 0x19bd154 && replace_object && ++pointer_reads % 2 == 0) {
        memcpy(out, &replace_object, 4); return 1;
    }
    memcpy(out, memory + a, n);
    return 1;
}
#include "../src/runtime/fex_game_timing_runtime.h"

static void put32(uint32_t a, uint32_t v) { memcpy(memory + a, &v, sizeof(v)); }
static void put64(uint32_t a, uint64_t v) { memcpy(memory + a, &v, sizeof(v)); }
static void *other_logger(void *unused)
{
    (void)unused;
    assert(!fex_log_metrics_batch);
    assert(fex_log_should_flush("[FEX3-FAULT] fail", 1, 0));
    assert(fex_log_should_flush("[EXC] access violation", 1, 1));
    return NULL;
}

int main(void)
{
    struct fex_game_timing s, before;
    memset(&s, 0x5a, sizeof(s)); before = s;
    assert(fex_game_snapshot(wine_nx_fex_timing_read, &s) == -1);
    assert(!memcmp(&s, &before, sizeof(s)));
    const unsigned char a[] = {0x55,0x8b,0xec,0x83,0xe4,0xf8,0x83,0xec,0x38,0xa1,0x40,0x41,0x5b,0x01,0x33,0xc4};
    const unsigned char b[] = {0x6a,0xff,0x68,0x4b,0xc9,0x33,0x01,0x64,0xa1,0,0,0,0,0x50,0x53,0x55};
    const unsigned char c[] = {0x51,0xd9,0xee,0xd8,0x1d,0xc8,0xe5,0x8a,1,0xdf,0xe0,0xf6,0xc4,0x41,0x7a,7};
    memcpy(memory+0x1119a60,a,sizeof(a)); memcpy(memory+0x1118170,b,sizeof(b));
    memcpy(memory+0x113ee10,c,sizeof(c));
    assert(!fex_game_snapshot(wine_nx_fex_timing_read, &s)); /* not initialized */
    put32(0x19bd154, 0xfffffffc);
    assert(!fex_game_snapshot(wine_nx_fex_timing_read, &s)); /* wrapped object */
    put32(0x19bd154, 0x2000001);
    assert(!fex_game_snapshot(wine_nx_fex_timing_read, &s)); /* bad alignment */
    put32(0x19bd154, 0x2000000);
    assert(fex_game_snapshot(wine_nx_fex_timing_read, &s) == -2);
    put32(0x2000000, 0x1503540); put32(0x2000020, 0x3f800000);
    put32(0x19bc826, 0x28b); put32(0x18ae57c, 15); put32(0x18ae580, 16);
    for (unsigned i = 0; i < 16; ++i) put64(0x18ae4f8 + i*8, 10000000 + i*16667);
    assert(fex_game_snapshot(wine_nx_fex_timing_read, &s) == 1);
    assert(s.object[8] == 0x3f800000 && s.settings == 0x28b);
    assert(fex_game_ring_time(&s) == 10250005 && fex_game_ring_gap(&s) == 16667);
    /* Guard-page/short-copy failures discard the whole snapshot, not a mix of
     * old/new output. No read failure mutates the last accepted snapshot. */
    before = s;
    const uint32_t failures[] = {0x1119a60,0x1118170,0x113ee10,0x19bd154,
                                0x2000000,0x18ae358,0x18ae4f8,0x19bc826};
    for (unsigned i = 0; i < sizeof(failures)/sizeof(failures[0]); ++i) {
        fail_address = failures[i];
        assert(!fex_game_snapshot(wine_nx_fex_timing_read, &s));
        assert(!memcmp(&s, &before, sizeof(s)));
    }
    fail_address = 0; replace_object = 0x2001000;
    assert(fex_game_snapshot(wine_nx_fex_timing_read, &s) == -3);
    replace_object = 0;
    s.pacer[0x84/4] = 16; assert(!fex_game_ring_time(&s) && !fex_game_ring_gap(&s));
    s = before; s.pacer[0x88/4] = 0; assert(!fex_game_ring_time(&s));
    s = before; s.pacer[30] = 0; s.pacer[31] = 0; assert(!fex_game_ring_gap(&s));
    fex_game_timing_report(); assert(!writes); /* config opt-in */
    fex_game_timing_enabled = 1; clock_tick = 1000000000;
    fex_game_timing_report(); assert(writes == 3 && strstr(output,"scale_bits=3f800000"));
    assert(strstr(output,"host_delta_us=0"));
    output[0] = 0; clock_tick += 5000000000ull;
    for (unsigned i = 0; i < 16; ++i) put64(0x18ae4f8 + i*8, 15000000 + i*16667);
    fex_game_timing_report();
    assert(strstr(output,"host_delta_us=5000000") && strstr(output,"ring_delta_us=5000000"));
    output[0] = 0; clock_tick += 5000000000ull;
    for (unsigned i = 0; i < 16; ++i) put64(0x18ae4f8 + i*8, 25000000 + i*16667);
    put32(0x2000020, 0x40000000);
    fex_game_timing_report();
    assert(strstr(output,"ring_delta_us=10000000") && strstr(output,"scale_bits=40000000"));
    assert(clock_tick == 11000000000ull); /* observer cannot advance or scale time */
    fex_log_metrics_batch = 1;
    for (unsigned i = 0; i < 32; ++i) assert(!fex_log_should_flush("[FEX3-PIPE] metrics",1,0));
    assert(fex_log_should_flush("[EXC] fault",1,1));
    assert(fex_log_should_flush("[EXIT] stop",1,1));
    assert(fex_log_should_flush("[FEX3] preflight",0,0));
    pthread_t t; assert(!pthread_create(&t,NULL,other_logger,NULL));
    assert(!pthread_join(t,NULL));
    fex_log_metrics_batch = 0;
    assert(fex_log_should_flush("[FEX3] startup",1,0));
    assert(!fex_log_should_flush("[PROGRESS] counters",1,0));
    puts("PASS: unsupported/unmapped/short reads, object reuse/overflow, ring validation, 1x/2x clock deltas, raw scale bits, disabled probe, no guest writes/waits, 32-line log batch and cross-thread fault flushing");
}
