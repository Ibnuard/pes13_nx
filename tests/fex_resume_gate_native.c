/* Real generated handlers; host pthreads model only libnx relative condvar,
 * object lookup, unrelated teardown services and reply transport. No target
 * scheduling or PES behavior claimed. All synchronization predicates locked. */
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

typedef uint64_t u64;
typedef struct { pthread_cond_t cond; } nx_cond;
typedef struct { pthread_mutex_t normal; } nx_mutex;
static int nx_lock(nx_mutex *m) { return pthread_mutex_lock(&m->normal); }
static int nx_unlock(nx_mutex *m) { return pthread_mutex_unlock(&m->normal); }
static int nx_signal(nx_cond *c) { return pthread_cond_signal(&c->cond); }
static int nx_destroy(nx_cond *c) { return pthread_cond_destroy(&c->cond); }
static unsigned broadcasts, signals;
static int counted_signal(nx_cond *c) { ++signals; return nx_signal(c); }
static int nx_broadcast(nx_cond *c) { ++broadcasts; return pthread_cond_broadcast(&c->cond); }
#define pthread_cond_t nx_cond
#define pthread_mutex_t nx_mutex
#define pthread_mutex_lock nx_lock
#define pthread_mutex_unlock nx_unlock
#define pthread_cond_signal counted_signal
#define pthread_cond_broadcast nx_broadcast
#define pthread_cond_destroy nx_destroy
#define NX_MUTEX_INITIALIZER { PTHREAD_MUTEX_INITIALIZER }
#define NX_COND_INITIALIZER { PTHREAD_COND_INITIALIZER }
/* Save host initialization through compound literal before replacing macro. */
static const nx_cond empty_cond = NX_COND_INITIALIZER;
#undef PTHREAD_COND_INITIALIZER
#define PTHREAD_COND_INITIALIZER empty_cond

struct horizon_server_object { struct horizon_thread_state thread; int refs, type; struct horizon_mutex_state mutex; };
struct horizon_server_connection { int reply_fd; unsigned tid; struct horizon_server_object *thread; };
struct horizon_server_handle_entry { struct horizon_server_object *object; struct horizon_server_handle_entry *next; };
struct req_header { unsigned op, size, reply_size; };
struct rep_header { unsigned error, size; };
struct horizon_suspend_thread_request { struct req_header header; unsigned handle, waited_handle; char pad[4]; };
struct horizon_suspend_thread_reply { struct rep_header header; int count; unsigned wait_handle; };
struct horizon_resume_thread_request { struct req_header header; unsigned handle; };
struct horizon_resume_thread_reply { struct rep_header header; int count; char pad[4]; };
static struct horizon_server_object target, other;
static struct horizon_server_connection owner = {1, 72, &target}, controller = {2, 4, &other};
static struct horizon_server_connection starter = {3, 4, &other};
static _Thread_local struct horizon_server_connection *current;
static pthread_mutex_t horizon_server_objects_mutex = NX_MUTEX_INITIALIZER;
static pthread_cond_t horizon_server_objects_cond;
static unsigned horizon_server_sleepers, trace_logs, event_phase, irrelevant, sleep_calls, timeout_calls;
static struct horizon_suspend_thread_reply replies[4];
static atomic_uint replies_ready[4];

static unsigned active_waits[4];
static void *active_conditions[4];
static unsigned waits[4], woke[4];

static int condvarWaitTimeout(void *condition, void *mutex, u64 ns)
{
    struct timespec deadline;
    assert(ns == 20000000); /* production 200000 * 100ns, not host fallback */
    clock_gettime(CLOCK_REALTIME, &deadline);
    deadline.tv_nsec += ns;
    if (deadline.tv_nsec >= 1000000000) { deadline.tv_nsec -= 1000000000; ++deadline.tv_sec; }
    unsigned fd = current->reply_fd;
    ++active_waits[fd]; ++waits[fd]; ++sleep_calls;
    active_conditions[fd] = condition;
    /* Underlying fields hold real host pthread types, not macro wrappers. */
    int status = pthread_cond_timedwait(condition, mutex, &deadline);
    assert(!status || status == ETIMEDOUT);
    --active_waits[fd]; active_conditions[fd] = NULL;
    if (status == ETIMEDOUT) ++timeout_calls;
    else {
        ++woke[fd];
        if (event_phase && fd == 1 && current->thread->thread.suspend) ++irrelevant;
    }
    return status;
}
static struct horizon_server_object *horizon_server_get_thread_locked(unsigned handle, unsigned *status)
{
    *status = 0;
    if (handle == 1 || handle == 11) return &target;
    if (handle == 2) return &other;
    if (handle == 0xfffffffeu) return current->thread;
    *status = 0xc0000008;
    return NULL;
}
/* Full targeted routing is deliberately disabled, never tested or enabled. */
static int wine_nx_fex_targeted_wake, fex_sync_router;
static void *fex_sync_resolve, *fex_sync_wake;
static void pes27_notify(void *r, const void *o, int n, void *a, void *b)
{ (void)r; (void)o; (void)n; (void)a; (void)b; assert(!"targeted router must stay disabled"); }
static void horizon_trace(const char *format, ...) { (void)format; }
static char last_trace[512];
static void wine_nx_runtime_trace(const char *line)
{
    assert(strlen(line) < sizeof(last_trace));
    strcpy(last_trace, line); ++trace_logs;
}
static void fex_suspend_observe(unsigned a, unsigned b, unsigned c, unsigned d, unsigned e)
{ (void)a; (void)b; (void)c; (void)d; (void)e; }
/* Unrelated teardown services are modeled; actual end_thread function sliced. */
#define HORIZON_SERVER_OBJECT_MUTEX 2
static struct horizon_server_handle_entry *horizon_server_handles;
static int horizon_server_running_threads, horizon_posted_messages, horizon_timers, horizon_clipboard;
static void horizon_server_end_completion_wait_locked(void *c) { (void)c; }
static long long horizon_server_now(void) { return 123; }
static void horizon_message_queue_drop(void *q, unsigned tid, int n) { (void)q; (void)tid; (void)n; }
static void horizon_win_timers_drop(void *q, unsigned tid, int n) { (void)q; (void)tid; (void)n; }
static int horizon_clip_thread_ended(void *q, unsigned tid) { (void)q; (void)tid; return 0; }
static void horizon_server_clipboard_notify_locked(void) { }
static void horizon_server_destroy_queue_locked(unsigned tid) { (void)tid; }
static void horizon_server_free_object(void *p) { (void)p; assert(!"test object must retain live reference"); }
static int horizon_server_write_reply(int fd, const void *data, size_t size, void *extra, int len)
{
    assert(fd >= 1 && fd <= 3);
    assert(size == sizeof(replies[fd]) && !extra && !len);
    assert(!pthread_mutex_lock(&horizon_server_objects_mutex));
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    memcpy(&replies[fd], data, size);
    atomic_fetch_add_explicit(&replies_ready[fd], 1, memory_order_release);
    return 0;
}
#include "handlers.inc"

static void tiny_wait(void) { struct timespec t = {0, 1000000}; nanosleep(&t, NULL); }
static void wait_active(unsigned fd)
{
    for (unsigned i = 0; i < 5000; ++i) {
        pthread_mutex_lock(&horizon_server_objects_mutex);
        int parked = active_waits[fd];
        pthread_mutex_unlock(&horizon_server_objects_mutex);
        if (parked) return;
        tiny_wait();
    }
    assert(!"waiter did not park");
}
static void *start_gate(void *unused)
{
    (void)unused; current = &starter;
    real_start_gate(&starter);
    atomic_fetch_add(&replies_ready[3], 1);
    return NULL;
}
static pthread_t launch_gate(void)
{
    pthread_t t;
    other.thread.started = 0; other.thread.suspend = 1;
    assert(!pthread_create(&t, NULL, start_gate, NULL));
    wait_active(3);
    return t;
}
static int resume(unsigned handle)
{
    struct horizon_resume_thread_request request = {.handle = handle};
    current = &controller;
    assert(!horizon_server_handle_resume_thread(&controller, (const void *)&request));
    assert(!replies[2].header.error);
    return replies[2].count;
}
static void *suspend_self(void *handle)
{
    struct horizon_suspend_thread_request request = {.handle = (unsigned)(uintptr_t)handle};
    current = &owner;
    assert(!horizon_server_handle_suspend_thread(&owner, (const void *)&request));
    return NULL;
}
static void reset(int started)
{
    memset(&target, 0, sizeof(target)); memset(&other, 0, sizeof(other));
    target.thread.tid = 72; target.thread.started = started; target.refs = 2;
    other.thread.tid = 4; other.thread.started = 1; other.refs = 2;
    owner.thread = &target; controller.thread = &other; starter.thread = &other;
    for (unsigned i = 0; i < 4; ++i) atomic_store(&replies_ready[i], 0);
    horizon_server_running_threads = 2;
}
static pthread_t launch(unsigned handle)
{
    pthread_t thread;
    assert(!pthread_create(&thread, NULL, suspend_self, (void *)(uintptr_t)handle));
    for (unsigned i = 0; i < 5000; ++i) {
        pthread_mutex_lock(&horizon_server_objects_mutex);
        int parked = target.thread.self_suspended && target.thread.suspend && active_waits[1];
        pthread_mutex_unlock(&horizon_server_objects_mutex);
        if (parked) return thread;
        tiny_wait();
    }
    assert(!"self request did not park"); return thread;
}
static void join_ok(pthread_t worker)
{
    assert(!pthread_join(worker, NULL));
    assert(atomic_load(&replies_ready[1]) == 1);
    assert(!replies[1].header.error && !replies[1].count && !replies[1].wait_handle);
    assert(!target.thread.suspend && !target.thread.self_suspended);
}
static unsigned suspend_remote(unsigned handle, int *count)
{
    struct horizon_suspend_thread_request request = {.handle = handle};
    current = &controller;
    assert(!horizon_server_handle_suspend_thread(&controller, (const void *)&request));
    *count = replies[2].count;
    return replies[2].header.error;
}
static void *suspend_second(void *unused)
{
    (void)unused;
    struct horizon_suspend_thread_request request = {.handle = 2};
    current = &starter;
    assert(!horizon_server_handle_suspend_thread(&starter, (const void *)&request));
    return NULL;
}
static void force_spurious(void *condition)
{
    /* Direct host signal: deliberate spurious wake, not runtime notifier. */
    assert(!nx_signal((nx_cond *)condition));
}
static void semantics_and_stress(void)
{
    int count;
    reset(1);
    other.thread.tid = target.thread.tid; /* equal tid is NOT object identity */
    assert(suspend_remote(1, &count) == HORIZON_THREADS_STATUS_NOT_SUPPORTED && count == 0);
    assert(suspend_remote(99, &count) == 0xc0000008u);
    target.thread.terminated = 1;
    assert(suspend_remote(1, &count) == HORIZON_THREADS_STATUS_ACCESS_DENIED);
    reset(1); target.thread.suspend = HORIZON_THREAD_MAX_SUSPEND;
    suspend_self((void *)1);
    assert(replies[1].header.error == HORIZON_THREADS_STATUS_SUSPEND_EXCEEDED);
    assert(!target.thread.self_suspended);

    /* No earlier resume credit. Nested, invalid and noop resumes neither signal
     * private waiters nor broadcast to unrelated live shared start gates. */
    reset(1); assert(resume(1) == 0);
    pthread_t worker = launch(11), gate = launch_gate();
    unsigned before = broadcasts, before_signals = signals;
    struct horizon_resume_thread_request invalid = {.handle = 99};
    current = &controller;
    assert(!horizon_server_handle_resume_thread(&controller, (const void *)&invalid));
    assert(replies[2].header.error == 0xc0000008u && replies[2].count == 0);
    for (int n = 1; n < HORIZON_THREAD_MAX_SUSPEND; ++n)
        assert(!suspend_remote(1, &count) && count == n);
    assert(suspend_remote(1, &count) == HORIZON_THREADS_STATUS_SUSPEND_EXCEEDED);
    for (int n = HORIZON_THREAD_MAX_SUSPEND; n > 1; --n) assert(resume(11) == n);
    assert(broadcasts == before && signals == before_signals);
    assert(!atomic_load(&replies_ready[1]));
    assert(resume(11) == 1); join_ok(worker);
    assert(signals == before_signals + 1 && broadcasts == before);
    assert(resume(1) == 0 && broadcasts == before && signals == before_signals + 1);
    /* Controller's pseudo handle resolves to start-gate object, not parked target. */
    assert(resume(0xfffffffeu) == 1); assert(!pthread_join(gate, NULL));
    assert(broadcasts == before + 1 && other.thread.started);

    /* Two synchronous waiters share identical tids but distinct object keys.
     * Pop older list node first: unlink must preserve newer stack waiter. */
    reset(1); other.thread.tid = target.thread.tid;
    worker = launch(0xfffffffeu);
    assert(!pthread_create(&gate, NULL, suspend_second, NULL)); wait_active(3);
    pthread_mutex_lock(&horizon_server_objects_mutex);
    void *second_condition = active_conditions[3];
    before_signals = signals;
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    assert(resume(11) == 1); join_ok(worker);
    pthread_mutex_lock(&horizon_server_objects_mutex);
    assert(signals == before_signals + 1 && other.thread.self_suspended);
    assert(active_conditions[3] == second_condition);
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    assert(!atomic_load(&replies_ready[3]));
    assert(resume(0xfffffffeu) == 1); assert(!pthread_join(gate, NULL));
    assert(!replies[3].header.error && !other.thread.self_suspended);

    /* Explicit spurious returns cannot release a suspended guest. A private
     * waiter still rechecks without any notifier after the original 20ms. */
    reset(1); worker = launch(1);
    pthread_mutex_lock(&horizon_server_objects_mutex);
    unsigned before_woke = woke[1];
    force_spurious(active_conditions[1]);
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    for (unsigned i = 0; i < 5000; ++i) {
        pthread_mutex_lock(&horizon_server_objects_mutex);
        int ready = woke[1] > before_woke && active_waits[1];
        pthread_mutex_unlock(&horizon_server_objects_mutex);
        if (ready) break;
        assert(i != 4999); tiny_wait();
    }
    assert(!atomic_load(&replies_ready[1]));
    pthread_mutex_lock(&horizon_server_objects_mutex);
    unsigned before_timeout = timeout_calls;
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    for (unsigned i = 0; i < 5000; ++i) {
        pthread_mutex_lock(&horizon_server_objects_mutex);
        int ready = timeout_calls > before_timeout;
        pthread_mutex_unlock(&horizon_server_objects_mutex);
        if (ready) break;
        assert(i != 4999); tiny_wait();
    }
    assert(!atomic_load(&replies_ready[1]));
    assert(resume(11) == 1); join_ok(worker);

    /* Count/status at CREATE_SUSPENDED gate, including overflow and nesting. */
    reset(0);
    for (int n = 0; n < HORIZON_THREAD_MAX_SUSPEND; ++n)
        assert(!suspend_remote(1, &count) && count == n);
    assert(suspend_remote(1, &count) == HORIZON_THREADS_STATUS_SUSPEND_EXCEEDED);
    for (int n = HORIZON_THREAD_MAX_SUSPEND; n; --n) assert(resume(1) == n);

    for (unsigned n = 0; n < 1000; ++n) {
        reset(1); worker = launch(n % 2 ? 11 : 0xfffffffeu);
        if (n % 13 == 0) tiny_wait();
        assert(resume(n % 2 ? 1 : 11) == 1); join_ok(worker);
    }
    assert(!horizon_server_sleepers && !active_waits[1] && !active_waits[3]);
}
int main(void)
{
    alarm(50);
    horizon_server_objects_cond = PTHREAD_COND_INITIALIZER;
    reset(1);
    pthread_t worker = launch(0xfffffffeu);
    pthread_t gate = launch_gate();
    pthread_mutex_lock(&horizon_server_objects_mutex); event_phase = 1;
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    for (unsigned i = 0; i < 40; ++i) {
        pthread_mutex_lock(&horizon_server_objects_mutex);
        fex_sync_signal_object_locked(&other); /* actual shared event notification helper */
        pthread_mutex_unlock(&horizon_server_objects_mutex);
        tiny_wait();
        assert(!atomic_load_explicit(&replies_ready[1], memory_order_acquire));
    }
    pthread_mutex_lock(&horizon_server_objects_mutex); event_phase = 0;
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    assert(resume(11) == 1); join_ok(worker);
    assert(!atomic_load(&replies_ready[3]));
    assert(resume(2) == 1); assert(!pthread_join(gate, NULL));
    printf("event probe: irrelevant=%u shared_broadcasts=%u sleeps=%u rechecks=%u\n",
           irrelevant, broadcasts, sleep_calls, timeout_calls);
    if (irrelevant) { puts("FAIL irrelevant self-suspend wake"); return 42; }
    reset(1); worker = launch(1);
    gate = launch_gate();
    pthread_mutex_lock(&horizon_server_objects_mutex);
    struct horizon_server_connection ended = owner;
    unsigned before_signals = signals;
    unsigned before_broadcasts = broadcasts;
    /* Keep observer connection alive as real parked RPC's object reference. */
    horizon_server_end_thread_locked(&ended);
    int explicitly_woken = signals == before_signals + 1;
    assert(broadcasts == before_broadcasts + 1); /* broad termination wake retained */
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    assert(!pthread_join(worker, NULL));
    assert(replies[1].header.error == HORIZON_THREADS_STATUS_ACCESS_DENIED);
    assert(!target.thread.self_suspended && !ended.thread);
    assert(horizon_server_running_threads == 1 && target.refs == 1);
    assert(resume(2) == 1); assert(!pthread_join(gate, NULL));
    if (!explicitly_woken) { puts("FAIL termination missing private wake"); return 43; }
    semantics_and_stress();
    assert(!trace_logs);
#ifdef FEX_RESUME_TEST
    assert(!fex_resume_waiters && !fex_resume_counts.active);
    assert(fex_resume_counts.waits == fex_resume_counts.returns);
    assert(fex_resume_counts.wakes == signals && fex_resume_counts.term_wakes == 1);
    assert(fex_self_suspend_waits == 1006 && fex_self_suspend_returns == 1006);
    wine_nx_fex_resume_report(); assert(trace_logs == 1);
    assert(strstr(last_trace, "[FEX3-RESUME] waits=") && strstr(last_trace, " active=0"));
    puts(last_trace);
    wine_nx_fex_resume_report(); assert(trace_logs == 1);
#endif
    printf("PASS resume-gate: 1000 concurrent cycles; aliases/pseudo/identity, nested/noop/invalid, "
           "start gate, explicit termination+broad wake, spurious/20ms recheck; "
           "waits=%llu returns=%llu signals=%u no hot logs\n",
           (unsigned long long)fex_self_suspend_waits,
           (unsigned long long)fex_self_suspend_returns, signals);
    return 0;
}
