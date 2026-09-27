/* Host mocks adapted from autorunhq/autorun check_waitable_timer.py,
 * commit 51f94949d738c978bfb80a5118d7ffa4cf6b98ae.
 * Tested functions are extracted verbatim from supplied Horizon source.
 * This is not a Switch kernel or PES13 end-to-end reproduction. */

#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stddef.h>
#include <stdint.h>
#include <limits.h>

#define HORIZON_STATUS_SUCCESS 0
#define HORIZON_STATUS_INVALID_HANDLE 0xc0000008u
#define HORIZON_CURRENT_THREAD_HANDLE 0xfffffffeu
#define HORIZON_STATUS_TIMEOUT 0x102u
#define HORIZON_STATUS_INVALID_PARAMETER 0xc000000du
#define HORIZON_STATUS_ABANDONED_WAIT_0 0x80u
#define HORIZON_SERVER_WAIT_SLICE 200000LL
#define HORIZON_SERVER_POLL_INTERVAL 10000LL
#define HORIZON_APC_RESULT_SIZE 40
#define TRACE(...) ((void)0)
#define FALSE 0
#define TRUE 1
enum { HORIZON_SELECT_WAIT = 1, HORIZON_SELECT_WAIT_ALL, HORIZON_SELECT_SIGNAL_AND_WAIT,
       HORIZON_SELECT_KEYED_EVENT_WAIT, HORIZON_SELECT_KEYED_EVENT_RELEASE };
#define max(a,b) ((a) > (b) ? (a) : (b))

typedef struct { long long QuadPart; } LARGE_INTEGER;
enum { HORIZON_SERVER_OBJECT_TIMER = 1, HORIZON_SERVER_OBJECT_MSG_QUEUE,
       HORIZON_SERVER_OBJECT_EVENT, HORIZON_SERVER_OBJECT_MUTEX,
       HORIZON_SERVER_OBJECT_SEMAPHORE, HORIZON_SERVER_OBJECT_THREAD };

struct horizon_server_object
{
    int type;
    int manual_reset;
    int signaled;
    long long timer_when;
    unsigned int timer_period;
};
struct horizon_server_handle_entry
{
    struct horizon_server_handle_entry *next;
    unsigned int handle;
    struct horizon_server_object *object;
};
struct horizon_server_connection { int reply_fd; const void *thread; };
struct horizon_set_timer_request { unsigned int handle; long long expire; int period; };
struct horizon_set_timer_reply { struct { unsigned int error; } header; int signaled; };
struct horizon_cancel_timer_request { unsigned int handle; };
struct horizon_cancel_timer_reply { struct { unsigned int error; } header; int signaled; };
struct horizon_get_timer_info_request { unsigned int handle; };
struct horizon_get_timer_info_reply { struct { unsigned int error; } header; long long when; int signaled; };
struct horizon_select_request { unsigned int size; long long timeout; };
struct horizon_select_reply { struct { unsigned int error; } header; int signaled; };
struct horizon_select_wait_op { int op; unsigned int handles[1]; };
struct horizon_select_signal_and_wait_op { int op; unsigned int wait, signal; };

static long long clock_ns100 = 130000000000000000LL;   /* an ordinary NT time */
static long long performance_ns100 = 1000000LL;
static unsigned clock_reads;
static void NtQuerySystemTime( LARGE_INTEGER *now ) { ++clock_reads; now->QuadPart = clock_ns100; }
static void NtQueryPerformanceCounter(LARGE_INTEGER *now, void *frequency)
{ (void)frequency; now->QuadPart = performance_ns100; }

static struct horizon_server_object objects[3];
static struct horizon_server_handle_entry entries[3] = {
    { &entries[1], 1, &objects[0] }, { &entries[2], 2, &objects[1] },
    { NULL, 3, &objects[2] } };
static struct horizon_server_handle_entry *horizon_server_handles = entries;
static int horizon_server_timers_armed;

static struct horizon_server_handle_entry *horizon_server_find_handle_locked( unsigned int handle )
{
    struct horizon_server_handle_entry *entry;

    for (entry = horizon_server_handles; entry; entry = entry->next)
        if (entry->handle == handle) return entry;
    return NULL;
}

static unsigned int horizon_server_find_typed_object_locked( unsigned int handle, int type,
                                                             struct horizon_server_object **out )
{
    struct horizon_server_handle_entry *entry = horizon_server_find_handle_locked( handle );

    if (!entry || entry->object->type != type) return HORIZON_STATUS_INVALID_HANDLE;
    *out = entry->object;
    return HORIZON_STATUS_SUCCESS;
}

/* Both replies carry the same error and previous state. */
static struct horizon_set_timer_reply last_reply;
static struct horizon_get_timer_info_reply last_info;
static int horizon_server_write_reply( int fd, const void *data, unsigned int size,
                                       const void *extra, unsigned int extra_size )
{
    (void)fd; (void)extra; (void)extra_size;
    if (size == sizeof(last_info)) memcpy(&last_info, data, size);
    else {
        assert( size == sizeof(last_reply) );
        memcpy( &last_reply, data, size );
    }
    return 0;
}

static int locked;
static int pthread_mutex_lock( void *m ) { (void)m; assert(!locked); locked = 1; return 0; }
static int pthread_mutex_unlock( void *m ) { (void)m; assert(locked); locked = 0; return 0; }
static struct { int normal; } horizon_server_objects_mutex;
typedef struct { int cond; } pthread_cond_t;
#define PTHREAD_COND_INITIALIZER {0}
typedef uint64_t u64;
static pthread_cond_t horizon_server_objects_cond;
static unsigned horizon_server_sleepers;
static unsigned sleeps, signal_attempts;
static void (*sleep_hook)(void);
static long long largest_sleep;
static void condvarWaitTimeout(int *condition, int *mutex, u64 ns)
{
    assert(condition && mutex == &horizon_server_objects_mutex.normal);
    assert(locked && ns > 0 && ns % 100 == 0 && ++sleeps <= 100);
    long long timeout = (long long)(ns / 100);
    assert(timeout <= HORIZON_SERVER_WAIT_SLICE);
    if (timeout > largest_sleep) largest_sleep = timeout;
    clock_ns100 += timeout;
    performance_ns100 += timeout;
    if (sleep_hook) sleep_hook(); /* Other client during atomic unlock/wait. */
}
int wine_nx_fex_targeted_wake;
static int pthread_cond_signal(void *p) { assert(p); return 0; }
static int pthread_cond_broadcast(void *p) { assert(p); return 0; }
static void *horizon_server_get_thread_locked(unsigned handle, unsigned *status)
{
    assert(handle == HORIZON_CURRENT_THREAD_HANDLE);
    *status = HORIZON_STATUS_SUCCESS;
    return &objects[2];
}
static void horizon_server_refresh_queues_locked(void) {}
/* Event signaling mocked; real dispatch must call once, not each poll. */
static unsigned horizon_server_signal_object_locked(unsigned handle)
{
    ++signal_attempts;
    if (handle != 3) return HORIZON_STATUS_INVALID_HANDLE;
    objects[2].signaled = 1;
    return HORIZON_STATUS_SUCCESS;
}

#include "fex_runtime_fixes_source.inc"
#define timer_is_signaled horizon_server_object_is_signaled
#define timer_consume_signal horizon_server_consume_signal

static void query_timer(unsigned handle)
{
    struct horizon_get_timer_info_request request = {handle};
    struct horizon_server_connection connection = {.reply_fd = 1};
    horizon_server_handle_get_timer_info(&connection, (const unsigned char *)&request);
}

static void select_op(const void *op, unsigned size, long long deadline, int apc)
{
    struct horizon_select_request request = {size, deadline};
    struct horizon_server_connection connection = {.reply_fd = 1};
    _Alignas(8) unsigned char data[128] = {0};
    unsigned offset = apc ? HORIZON_APC_RESULT_SIZE : 0;
    assert(offset + size <= sizeof(data));
    memcpy(data + offset, op, size);
    sleeps = signal_attempts = 0;
    largest_sleep = 0;
    horizon_server_handle_select(&connection, (const unsigned char *)&request,
                                 data, offset + size);
    assert(!locked && !horizon_server_sleepers);
#ifdef FEX_RUNTIME_FIXES_SYNC
    assert(!fex_sync_router.head);
#endif
}
static void wait_timer(long long deadline)
{
    struct horizon_select_wait_op op = {HORIZON_SELECT_WAIT, {1}};
    select_op(&op, sizeof(op), deadline, 0);
}

static void set_timer(unsigned handle, long long expire, int period)
{
    struct horizon_set_timer_request request = {handle, expire, period};
    struct horizon_server_connection connection = {.reply_fd = 1};
    horizon_server_handle_set_timer(&connection, (const unsigned char *)&request);
}
static void cancel_timer(unsigned handle)
{
    struct horizon_cancel_timer_request request = {handle};
    struct horizon_server_connection connection = {.reply_fd = 1};
    horizon_server_handle_cancel_timer(&connection, (const unsigned char *)&request);
}
#define MS 10000LL
static void run_tests(void)
{
    (void)NtQuerySystemTime; /* Pin has no clock read; RED still compiles. */
    (void)pthread_cond_signal;
    (void)pthread_cond_broadcast;
    objects[0].type = HORIZON_SERVER_OBJECT_TIMER;
    objects[1].type = HORIZON_SERVER_OBJECT_MSG_QUEUE;
    objects[2].type = HORIZON_SERVER_OBJECT_EVENT;
    objects[2].manual_reset = 1;
    set_timer(1, -16 * MS, 0);
    assert(!last_reply.header.error && !last_reply.signaled);
    assert(!objects[0].signaled); /* RED on actual pin: signalled on set. */
    assert(objects[0].timer_when == clock_ns100 + 16 * MS);
    assert(horizon_server_handle_polls_locked(1));
    assert(horizon_server_handle_polls_locked(2));
    assert(!horizon_server_handle_polls_locked(0));
    assert(!horizon_server_handle_polls_locked(99));
    assert(!horizon_server_handle_polls_locked(HORIZON_CURRENT_THREAD_HANDLE));
    horizon_server_update_timers_locked();
    assert(!objects[0].signaled);
    clock_ns100 += 16 * MS - 1;
    horizon_server_update_timers_locked();
    assert(!objects[0].signaled);
    clock_ns100++;
    horizon_server_update_timers_locked();
    assert(objects[0].signaled && !objects[0].timer_when);
    assert(!horizon_server_handle_polls_locked(1));
    assert(!horizon_server_timers_armed);

    set_timer(1, -MS, 16);
    assert(last_reply.signaled && !objects[0].signaled);
    clock_ns100 += MS;
    horizon_server_update_timers_locked();
    assert(objects[0].signaled && objects[0].timer_when == clock_ns100 + 16 * MS);
    clock_ns100 += 100 * MS;
    horizon_server_update_timers_locked();
    assert(objects[0].signaled && objects[0].timer_when > clock_ns100);
    assert(objects[0].timer_when <= clock_ns100 + 16 * MS);

    set_timer(1, clock_ns100 + 5 * MS, 0);
    assert(objects[0].timer_when == clock_ns100 + 5 * MS);
    set_timer(1, clock_ns100 - 5 * MS, 0);
    assert(objects[0].timer_when == clock_ns100);
    horizon_server_update_timers_locked();
    assert(objects[0].signaled);
    set_timer(1, 0, -5);
    assert(!objects[0].signaled && objects[0].timer_when == clock_ns100);
    assert(!objects[0].timer_period);
    horizon_server_update_timers_locked();
    assert(objects[0].signaled);

    /* Cancel before expiry: no later signal, no periodic restart. */
    set_timer(1, -MS, 16);
    cancel_timer(1);
    assert(!last_reply.signaled && !objects[0].signaled);
    assert(!objects[0].timer_when && !objects[0].timer_period);
    clock_ns100 += 1000 * MS;
    horizon_server_update_timers_locked();
    assert(!objects[0].signaled && !horizon_server_timers_armed);
    set_timer(2, -MS, 0);
    assert(last_reply.header.error == HORIZON_STATUS_INVALID_HANDLE);
    assert(!horizon_server_timers_armed);
    cancel_timer(99);
    assert(last_reply.header.error == HORIZON_STATUS_INVALID_HANDLE);
    /* CancelWaitableTimer must NOT change signaled state. Upstream's
     * check_waitable_timer.py expects clearing here; Microsoft says otherwise.
     * https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-cancelwaitabletimer */
    for (int manual = 0; manual <= 1; ++manual)
    {
        objects[0].manual_reset = manual;
        set_timer(1, -MS, 16);
        clock_ns100 += MS;
        horizon_server_update_timers_locked();
        assert(objects[0].signaled);
        cancel_timer(1);
        assert(last_reply.signaled && objects[0].signaled);
        assert(!objects[0].timer_when && !objects[0].timer_period);
        clock_ns100 += 1000 * MS;
        horizon_server_update_timers_locked();
        assert(objects[0].signaled && !horizon_server_timers_armed);
    }
    /* Real consume switch: auto timer resets exactly once; manual persists. */
    objects[0].manual_reset = 0;
    assert(timer_is_signaled(&objects[0]));
    timer_consume_signal(&objects[0]);
    assert(!timer_is_signaled(&objects[0]));
    horizon_server_update_timers_locked();
    assert(!timer_is_signaled(&objects[0]));
    objects[0].manual_reset = 1;
    set_timer(1, -MS, 0);
    clock_ns100 += MS;
    query_timer(1); /* Query must process expiry even without a wait. */
    assert(!last_info.header.error && last_info.signaled && !last_info.when);
    timer_consume_signal(&objects[0]);
    assert(timer_is_signaled(&objects[0]));
    query_timer(99);
    assert(last_info.header.error == HORIZON_STATUS_INVALID_HANDLE);
    unsigned reads = clock_reads;
    horizon_server_update_timers_locked();
    assert(clock_reads == reads); /* Idle fast path skips even clock read. */

    /* Actual select loop: due timer wakes by 1ms polling, not immediately. */
    objects[0].manual_reset = 0;
    set_timer(1, -16 * MS, 0);
    long long start = clock_ns100;
    wait_timer(0x7fffffffffffffffLL);
    assert(!last_reply.header.error && sleeps == 16 && clock_ns100 == start + 16 * MS);
    assert(largest_sleep == MS && !objects[0].signaled);
    set_timer(1, -16 * MS, 0);
    wait_timer(0);
    assert(last_reply.header.error == HORIZON_STATUS_TIMEOUT && !sleeps);
    wait_timer(clock_ns100 + 3 * MS);
    assert(last_reply.header.error == HORIZON_STATUS_TIMEOUT && sleeps == 3);
    assert(!objects[0].signaled);
    cancel_timer(1);
    /* Real dispatcher: APC prefix, WAIT_ALL, WAIT_ANY and signal only once. */
    struct { int op; unsigned handles[2]; } pair = {HORIZON_SELECT_WAIT_ALL, {3, 1}};
    objects[2].signaled = 1;
    set_timer(1, -4 * MS, 0);
    select_op(&pair, sizeof(pair), LLONG_MAX, 1);
    assert(!last_reply.header.error && sleeps == 4 && largest_sleep == MS);
    pair.op = HORIZON_SELECT_WAIT;
    objects[2].signaled = 0;
    set_timer(1, -2 * MS, 0);
    select_op(&pair, sizeof(pair), LLONG_MAX, 0);
    assert(last_reply.header.error == 1 && sleeps == 2);
    struct horizon_select_signal_and_wait_op signal_wait = {HORIZON_SELECT_SIGNAL_AND_WAIT, 1, 3};
    set_timer(1, -3 * MS, 0);
    select_op(&signal_wait, sizeof(signal_wait), LLONG_MAX, 1);
    assert(!last_reply.header.error && sleeps == 3 && signal_attempts == 1);
    assert(objects[2].signaled && !objects[0].signaled);

    /* Monotonic deadline, sub-millisecond deadline and expired deadline. */
    set_timer(1, -16 * MS, 0);
    wait_timer(-(performance_ns100 + 3 * MS));
    assert(last_reply.header.error == HORIZON_STATUS_TIMEOUT && sleeps == 3);
    wait_timer(clock_ns100 + MS / 2);
    assert(last_reply.header.error == HORIZON_STATUS_TIMEOUT && sleeps == 1 && largest_sleep == MS / 2);
    wait_timer(-(performance_ns100 - 1));
    assert(last_reply.header.error == HORIZON_STATUS_TIMEOUT && !sleeps);
    cancel_timer(1);
    wait_timer(clock_ns100 + 45 * MS);
    assert(last_reply.header.error == HORIZON_STATUS_TIMEOUT && sleeps == 3);
    assert(largest_sleep == HORIZON_SERVER_WAIT_SLICE); /* Inactive timer must not busy poll. */
    struct horizon_select_wait_op invalid = {HORIZON_SELECT_WAIT, {99}};
    select_op(&invalid, sizeof(invalid), LLONG_MAX, 0);
    assert(last_reply.header.error == HORIZON_STATUS_INVALID_HANDLE && !sleeps);

    /* Handle aliases do not repeat a periodic expiry while scanning handles. */
    entries[2].object = &objects[0];
    set_timer(1, -MS, 3);
    clock_ns100 += MS;
    horizon_server_update_timers_locked();
    assert(objects[0].timer_when == clock_ns100 + 3 * MS);
    timer_consume_signal(&objects[0]);
    horizon_server_update_timers_locked();
    assert(!objects[0].signaled);
    entries[2].object = &objects[2];
    cancel_timer(1);
    puts("PASS timers: expiry, rearm, periods, reset modes, cancel preserves signal, query, select polling/deadlines");
}

static void rearm_while_waiting(void)
{
    sleep_hook = NULL;
    locked = 0;
    set_timer(1, -16 * MS, 0);
    locked = 1;
}

static void rearm_poll_test(void)
{
    objects[0].type = HORIZON_SERVER_OBJECT_TIMER;
    cancel_timer(1);
    long long start = clock_ns100;
    sleep_hook = rearm_while_waiting;
    wait_timer(LLONG_MAX);
    assert(!last_reply.header.error && !sleep_hook);
    assert(clock_ns100 == start + HORIZON_SERVER_WAIT_SLICE + 16 * MS);
    assert(sleeps == 17); /* First wait unarmed; rearm must enable 1ms polling. */
    puts("PASS timer rearm during wait: polling state refreshes after wake");
}

static void relative_overflow_test(void)
{
    objects[0].type = HORIZON_SERVER_OBJECT_TIMER;
    set_timer(1, LLONG_MIN, 0);
    assert(!last_reply.header.error && !objects[0].signaled);
    assert(objects[0].timer_when == LLONG_MAX);
    horizon_server_update_timers_locked();
    assert(!objects[0].signaled);
    cancel_timer(1);
    puts("PASS timer relative overflow: distant expiry saturates without UB");
}

static void cancel_while_waiting(void)
{
    sleep_hook = NULL;
    locked = 0;
    cancel_timer(1);
    locked = 1;
}

static void cancel_poll_test(void)
{
    objects[0].type = HORIZON_SERVER_OBJECT_TIMER;
    set_timer(1, -16 * MS, 0);
    long long start = clock_ns100;
    sleep_hook = cancel_while_waiting;
    wait_timer(start + 45 * MS);
    assert(last_reply.header.error == HORIZON_STATUS_TIMEOUT && !sleep_hook);
    assert(sleeps == 4 && largest_sleep == HORIZON_SERVER_WAIT_SLICE);
    assert(!objects[0].signaled && !horizon_server_timers_armed);
    puts("PASS timer cancel during wait: inactive timer leaves 1ms polling");
}

static void periodic_overflow_test(void)
{
    objects[0].type = HORIZON_SERVER_OBJECT_TIMER;
    long long saved = clock_ns100;
    clock_ns100 = LLONG_MAX - MS;
    set_timer(1, 0, 2);
    horizon_server_update_timers_locked();
    assert(objects[0].signaled && !objects[0].timer_when && !horizon_server_timers_armed);
    timer_consume_signal(&objects[0]);
    horizon_server_update_timers_locked();
    assert(!objects[0].signaled);
    clock_ns100 = saved;
    puts("PASS timer periodic overflow: no representable next deadline, no repeated signal");
}

static void periodic_catchup_test(void)
{
    objects[0].type = HORIZON_SERVER_OBJECT_TIMER;
    set_timer(1, -MS, 1);
    clock_ns100 += 1000000000000000LL;
    horizon_server_update_timers_locked();
    assert(objects[0].signaled && objects[0].timer_when == clock_ns100 + MS);
    cancel_timer(1);
    puts("PASS timer periodic catch-up: constant work after long clock gap");
}

static void scenario(const char *name)
{
    if (!strcmp(name, "normal")) run_tests();
    else if (!strcmp(name, "rearm-poll")) rearm_poll_test();
    else if (!strcmp(name, "cancel-poll")) cancel_poll_test();
    else if (!strcmp(name, "relative-overflow")) relative_overflow_test();
    else if (!strcmp(name, "periodic-overflow")) periodic_overflow_test();
    else if (!strcmp(name, "periodic-catchup")) periodic_catchup_test();
    else assert(!"unknown timer scenario");
}

int main(int argc, char **argv)
{
    const char *name = argc == 2 ? argv[1] : "normal";
    scenario(name);
#ifdef FEX_RUNTIME_FIXES_SYNC
    memset(objects, 0, sizeof(objects));
    wine_nx_fex_targeted_wake = 1;
    scenario(name);
    if (!strcmp(name, "normal") || !strcmp(name, "rearm-poll")) assert(fex_sync_router.sleeps > 0);
    puts("PASS native sync: real shared/targeted router and condvar sleep paths");
#endif
    return 0;
}
