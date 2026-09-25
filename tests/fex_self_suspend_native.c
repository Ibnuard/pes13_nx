/* Real patched server handlers + real thread state, with pthread clients.
 * Only handle lookup and reply transport are modeled; the wait/resume loop
 * is the shipping code. Compile under ASan/UBSan in WSL. */
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include "horizon_threads.h"

struct horizon_server_object { struct horizon_thread_state thread; };
struct horizon_server_connection { int reply_fd; unsigned tid; struct horizon_server_object *thread; };
struct req_header { unsigned op, size, reply_size; };
struct rep_header { unsigned error, size; };
struct horizon_suspend_thread_request { struct req_header header; unsigned handle, waited_handle; char pad[4]; };
struct horizon_suspend_thread_reply { struct rep_header header; int count; unsigned wait_handle; };
struct horizon_resume_thread_request { struct req_header header; unsigned handle; };
struct horizon_resume_thread_reply { struct rep_header header; int count; char pad[4]; };
static struct horizon_server_object target, other;
static struct horizon_server_connection owner = {1, 72, &target}, controller = {2, 4, &other};
static _Thread_local struct horizon_server_connection *current;
static pthread_mutex_t horizon_server_objects_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t changed = PTHREAD_COND_INITIALIZER;
static unsigned sleepers, sleep_calls, trace_logs;
static struct horizon_suspend_thread_reply replies[3];
static atomic_uint replies_ready[3];
#define HORIZON_SERVER_WAIT_SLICE 200000LL

static struct horizon_server_object *horizon_server_get_thread_locked(unsigned handle, unsigned *status)
{
    *status = 0;
    if (handle == 1 || handle == 11) return &target;
    if (handle == 2) return &other;
    if (handle == 0xfffffffeu) return current->thread;
    *status = 0xc0000008;
    return NULL;
}
static void horizon_server_signal_changed_locked(void) { if (sleepers) pthread_cond_broadcast(&changed); }
static void horizon_server_sleep_locked(long long timeout)
{
    struct timespec deadline;
    assert(timeout == HORIZON_SERVER_WAIT_SLICE);
    clock_gettime(CLOCK_REALTIME, &deadline);
    deadline.tv_nsec += timeout * 100;
    if (deadline.tv_nsec >= 1000000000) { deadline.tv_nsec -= 1000000000; ++deadline.tv_sec; }
    ++sleepers; ++sleep_calls;
    int status = pthread_cond_timedwait(&changed, &horizon_server_objects_mutex, &deadline);
    assert(!status || status == ETIMEDOUT);
    --sleepers;
}
static void horizon_trace(const char *format, ...) { (void)format; }
static void wine_nx_runtime_trace(const char *line) { assert(strlen(line) < 256); ++trace_logs; }
static int horizon_server_write_reply(int fd, const void *data, size_t size, void *extra, int len)
{
    assert(fd == 1 || fd == 2);
    assert(size == sizeof(replies[fd]) && !extra && !len);
    /* The response cannot be sent with the server object mutex held. */
    assert(!pthread_mutex_lock(&horizon_server_objects_mutex));
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    memcpy(&replies[fd], data, size);
    atomic_fetch_add_explicit(&replies_ready[fd], 1, memory_order_release);
    return 0;
}

/* Generated from the actual patched horizon.c, not a parallel implementation. */
#include "fex_self_suspend_handlers.inc"

static int resume(unsigned handle)
{
    struct horizon_resume_thread_request request = {.handle = handle};
    current = &controller;
    assert(!horizon_server_handle_resume_thread(&controller, (const void *)&request));
    assert(!replies[2].header.error);
    return replies[2].count;
}
static unsigned suspend_other(unsigned handle, int *count)
{
    struct horizon_suspend_thread_request request = {.handle = handle};
    current = &controller;
    assert(!horizon_server_handle_suspend_thread(&controller, (const void *)&request));
    *count = replies[2].count;
    return replies[2].header.error;
}
static void *suspend_self(void *handle)
{
    struct horizon_suspend_thread_request request = {.handle = (unsigned)(uintptr_t)handle};
    current = &owner;
    assert(!horizon_server_handle_suspend_thread(&owner, (const void *)&request));
    return NULL;
}
static void tiny_wait(void)
{
    struct timespec t = {0, 1000000};
    nanosleep(&t, NULL);
}
static void wait_parked(void)
{
    for (unsigned i = 0; i < 5000; ++i) {
        pthread_mutex_lock(&horizon_server_objects_mutex);
        int parked = target.thread.self_suspended && target.thread.suspend && sleepers;
        pthread_mutex_unlock(&horizon_server_objects_mutex);
        if (parked) return;
        tiny_wait();
    }
    assert(!"self request did not park");
}
static void reset(int started)
{
    memset(&target, 0, sizeof(target)); memset(&other, 0, sizeof(other));
    target.thread.tid = 72; target.thread.started = started;
    other.thread.tid = 4; other.thread.started = 1;
    atomic_store(&replies_ready[1], 0); atomic_store(&replies_ready[2], 0);
}
static pthread_t launch(unsigned handle)
{
    pthread_t thread;
    assert(!pthread_create(&thread, NULL, suspend_self, (void *)(uintptr_t)handle));
    wait_parked();
    assert(!atomic_load_explicit(&replies_ready[1], memory_order_acquire));
    return thread;
}
static void join_ok(pthread_t thread)
{
    assert(!pthread_join(thread, NULL));
    assert(atomic_load(&replies_ready[1]) == 1);
    assert(!replies[1].header.error && !replies[1].count && !replies[1].wait_handle);
    assert(!target.thread.suspend && !target.thread.self_suspended);
}

int main(void)
{
    alarm(60);
    int count;
    reset(0);
    for (int n = 0; n < HORIZON_THREAD_MAX_SUSPEND; ++n) {
        assert(!suspend_other(1, &count)); assert(count == n);
    }
    assert(suspend_other(1, &count) == HORIZON_THREADS_STATUS_SUSPEND_EXCEEDED);
    for (int n = HORIZON_THREAD_MAX_SUSPEND; n; --n) assert(resume(1) == n);
    reset(1);
    assert(suspend_other(1, &count) == HORIZON_THREADS_STATUS_NOT_SUPPORTED);
    assert(!target.thread.suspend && !target.thread.self_suspended);
    assert(suspend_other(99, &count) == 0xc0000008u);
    target.thread.terminated = 1;
    assert(suspend_other(1, &count) == HORIZON_THREADS_STATUS_ACCESS_DENIED);
    reset(1); target.thread.suspend = HORIZON_THREAD_MAX_SUSPEND;
    suspend_self((void *)1);
    assert(replies[1].header.error == HORIZON_THREADS_STATUS_SUSPEND_EXCEEDED);
    assert(!target.thread.self_suspended);

    /* An earlier resume is not a credit that can bypass a later suspend. */
    reset(1); assert(!resume(1));
    pthread_t worker = launch(0xfffffffeu);
    for (int i = 0; i < 40; ++i) {
        pthread_mutex_lock(&horizon_server_objects_mutex);
        horizon_server_signal_changed_locked();
        pthread_mutex_unlock(&horizon_server_objects_mutex);
        tiny_wait();
        assert(!atomic_load_explicit(&replies_ready[1], memory_order_acquire));
    }
    assert(!suspend_other(11, &count) && count == 1);
    assert(resume(1) == 2);
    tiny_wait();
    assert(!atomic_load_explicit(&replies_ready[1], memory_order_acquire));
    assert(resume(1) == 1); join_ok(worker);

    /* Nesting up to the limit while actually parked needs matching resumes. */
    reset(1); worker = launch(11);
    for (int n = 1; n < HORIZON_THREAD_MAX_SUSPEND; ++n)
        assert(!suspend_other(1, &count) && count == n);
    assert(suspend_other(1, &count) == HORIZON_THREADS_STATUS_SUSPEND_EXCEEDED);
    for (int n = HORIZON_THREAD_MAX_SUSPEND; n > 1; --n) assert(resume(1) == n);
    assert(!atomic_load_explicit(&replies_ready[1], memory_order_acquire));
    assert(resume(1) == 1); join_ok(worker);

    /* Object identity, rather than tid or handle value, defines self. */
    reset(1); other.thread.tid = target.thread.tid;
    assert(suspend_other(1, &count) == HORIZON_THREADS_STATUS_NOT_SUPPORTED);

    /* Server lifetime owns the parked object; terminate wakes with an error. */
    reset(1); worker = launch(1);
    pthread_mutex_lock(&horizon_server_objects_mutex);
    horizon_thread_mark_terminated(&target.thread, 123);
    horizon_server_signal_changed_locked();
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    assert(!pthread_join(worker, NULL));
    assert(replies[1].header.error == HORIZON_THREADS_STATUS_ACCESS_DENIED);
    assert(!target.thread.self_suspended);

    /* Resume immediately after seeing the locked predicate, or after a delay.
     * Repeat real concurrent handler calls to expose the lost-wakeup window. */
    for (unsigned n = 0; n < 1000; ++n) {
        reset(1); worker = launch(n % 2 ? 1 : 0xfffffffeu);
        if (n % 13 == 0) tiny_wait();
        assert(resume(11) == 1);
        join_ok(worker);
    }
    assert(fex_self_suspend_waits == 1003 && fex_self_suspend_returns == 1003);
    assert(!trace_logs); /* No diagnostics or SD I/O per suspend/resume. */
    wine_nx_fex_self_suspend_report();
    assert(trace_logs == 1);
    wine_nx_fex_self_suspend_report();
    assert(trace_logs == 1);
    printf("PASS self-suspend: 1000 concurrent park/resume cycles, no early reply or lost wake, "
           "nested counts/overflow, remote rejection, pseudo/alias handles, spurious wakes, "
           "termination, no per-call logs; waits=%llu returns=%llu sleeps=%u\n",
           (unsigned long long)fex_self_suspend_waits,
           (unsigned long long)fex_self_suspend_returns, sleep_calls);
    return 0;
}
