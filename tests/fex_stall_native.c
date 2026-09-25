/* Exercise the actual bounded observer with modeled kernel operations. */
#include <assert.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "horizon_host.h"
#include "horizon_stall.h"
#define NX_PROF_DEPTH 8
#define R_FAILED(v) ((v) != 0)
#define R_SUCCEEDED(v) ((v) == 0)
typedef unsigned Handle;
typedef unsigned Result;
typedef struct { uint64_t addr, size; } MemoryInfo;
typedef struct {
    union { uint64_t x; } cpu_gprs[29], pc;
    uint64_t lr, sp, fp;
} ThreadContext;
enum { ThreadActivity_Paused, ThreadActivity_Runnable };
struct nx_prof_row { Handle handle; unsigned tid, permille; char kind; int core; uint64_t teb; };
static pthread_mutex_t profile_mutex = PTHREAD_MUTEX_INITIALIZER;
static unsigned paused, logs, pauses, resumes, context_reads, resume_attempts, allowed = 1;
static unsigned fail_pause, fail_read, fail_resume_once;
static _Alignas(8) unsigned char code[256];
static uint64_t state[4];

static int readable(uint64_t addr, MemoryInfo *info) {
    uint64_t bases[] = {(uintptr_t)code, (uintptr_t)state};
    uint64_t sizes[] = {sizeof(code), sizeof(state)};
    for (unsigned i = 0; i < 2; ++i) if (addr >= bases[i] && addr - bases[i] < sizes[i]) {
        info->addr = bases[i]; info->size = sizes[i]; return 1;
    }
    return 0;
}
static int envIsSyscallHinted(unsigned n) { assert(n == 0x32 || n == 0x33); return allowed; }
static void svcSleepThread(int64_t ns) { assert(ns == 0 || ns == 2000000); }
static Result svcSetThreadActivity(Handle h, unsigned state_) {
    assert(h < 5);
    if (state_ == ThreadActivity_Paused) {
        ++pauses;
        if (h == fail_pause) return 3;
        assert(!paused); paused |= 1u << h;
    } else {
        ++resume_attempts;
        if (fail_resume_once) { fail_resume_once = 0; return 7; }
        assert(paused == (1u << h)); paused = 0; ++resumes;
    }
    return 0;
}
static Result svcGetThreadContext3(ThreadContext *ctx, Handle h) {
    assert(paused == (1u << h)); ++context_reads;
    if (h == fail_read) return 5;
    memset(ctx, 0, sizeof(*ctx));
    ctx->pc.x = (uintptr_t)code + 32;
    ctx->cpu_gprs[28].x = (uintptr_t)state;
    return 0;
}
static unsigned walk_callers(const ThreadContext *ctx, uint64_t *callers) {
    assert(paused); (void)ctx; callers[0] = 0xabc; return 1;
}
static void wine_nx_runtime_trace(const char *line) {
    assert(!paused); assert(strlen(line) < 960); ++logs;
}
static void *alias(const void *p, uint64_t size) {
    assert(paused); assert(size == 4); return (void *)((uintptr_t)p + 4096);
}
const struct pes13_fex_host *pes13_fex_native_host(void) {
    static const struct pes13_fex_host host = {.write_alias = alias};
    return &host;
}

#include "../src/runtime/fex_stall_probe.h"

/* Compile and exercise the real server observer as well. */
#define HORIZON_THREADS_STATUS_NOT_SUPPORTED 0xc00000bbu
static pthread_mutex_t horizon_server_objects_mutex = PTHREAD_MUTEX_INITIALIZER;
#include "../src/runtime/fex_suspend_observe.h"

int main(void) {
    struct pes13_fex_stall_gate gate = {0};
    for (unsigned t = 0; t <= 1000; t += 5) assert(!pes13_fex_stall_due(&gate, t * 60, t));
    assert(!pes13_fex_stall_due(&gate, 60000, 1005));
    assert(pes13_fex_stall_due(&gate, 60000, 1010));
    assert(!pes13_fex_stall_due(&gate, 60000, 1011));
    assert(pes13_fex_stall_due(&gate, 60000, 1015));
    assert(pes13_fex_stall_due(&gate, 60000, 1020));
    assert(!pes13_fex_stall_due(&gate, 60000, 1025));
    assert(!pes13_fex_stall_due(&gate, 70000, 1030));
    assert(!pes13_fex_stall_due(&gate, 70000, 1040));
    gate = (struct pes13_fex_stall_gate){0};
    for (unsigned t = 0; t < 1000; t += 5) assert(!pes13_fex_stall_due(&gate, 0, t));

    uint32_t offset = 128;
    memcpy(code, &offset, sizeof(offset));
    struct pes13_fex_observed_tail tail = {.size = 200, .rip = 0x401000, .guest_size = 40};
    memcpy(code + offset, &tail, sizeof(tail));
    state[0] = (uintptr_t)code; state[3] = 0x402000;
    uint64_t scratch;
    assert(!fex_stall_read(UINT64_MAX - 3, &scratch, 8));
    assert(!fex_stall_read((uintptr_t)state + sizeof(state) - 4, &scratch, 8));
    assert(fex_stall_read((uintptr_t)state + sizeof(state) - 8, &scratch, 8));
    assert(scratch == 0x402000);

    const struct nx_prof_row rows[] = {{2,72,800,'w',0,0}, {3,124,700,'w',0,0},
                                     {4,90,900,'s',0,0}, {1,4,10,'w',0,0}};
    wine_nx_fex_stall_targets(rows, 4);
    assert(fex_stall_targets[0].tid == 4 && fex_stall_targets[1].tid == 72 &&
           fex_stall_targets[2].tid == 124 && !fex_stall_targets[3].handle);
    wine_nx_fex_stall_probe(100, 10);
    wine_nx_fex_stall_probe(120, 15);
    wine_nx_fex_stall_probe(120, 20);
    assert(!logs && !pauses);
    fail_pause = 2; fail_read = 3; fail_resume_once = 1;
    wine_nx_fex_stall_probe(120, 25);
    assert(pauses == 6 && resumes == 4 && resume_attempts == 5 && !paused);
    assert(context_reads == 12); /* two successes plus 2x five failed attempts */
    unsigned old_logs = logs;
    wine_nx_fex_stall_remove(3);
    allowed = 0;
    wine_nx_fex_stall_probe(120, 30);
    assert(logs == old_logs + 1 && pauses == 6);
    allowed = 1; fail_pause = 0; fail_read = 0;
    wine_nx_fex_stall_probe(120, 35);
    assert(pauses == 10 && resumes == 8 && !paused);
    old_logs = logs;
    for (unsigned t = 40; t < 300; t += 5) wine_nx_fex_stall_probe(120, t);
    assert(logs == old_logs && pauses == 10);

    for (unsigned i = 0; i < 1000000; ++i) fex_suspend_observe(72, 4, 0xc00000bbu, 1, 0);
    fex_suspend_observe(124, 4, 0, 0, 0);
    assert(fex_suspend_rows[0].calls == 1000000 && fex_suspend_rows[0].rejected == 1000000);
    assert(fex_suspend_rows[1].calls == 1 && fex_suspend_rows[1].succeeded == 1);
    assert(logs == old_logs); /* no per-call logging */
    wine_nx_fex_suspend_report(); assert(logs == old_logs + 2);
    wine_nx_fex_suspend_report(); assert(logs == old_logs + 2);
    fex_suspend_observe(72, 4, 0xc0000022u, 1, 1);
    wine_nx_fex_suspend_report(); assert(logs == old_logs + 3);
    puts("PASS stall observer: idle suppression, bounded capture, resume on read failure, permission fallback, unregister, range checks, and 1M suspend observations without per-call I/O");
}
