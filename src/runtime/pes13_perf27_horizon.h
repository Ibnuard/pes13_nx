/* Included in horizon.c where the original shared wait implementation stood. */
#include "pes13_perf27_wait.h"
static struct pes27_router pes27_router;
static int pes27_targeted;
static pthread_once_t pes27_once = PTHREAD_ONCE_INIT;
static struct horizon_server_handle_entry *horizon_server_find_handle_locked(unsigned int);

static void pes27_init(void)
{
    FILE *f = fopen("sdmc:/switch/pes13-nx/perf27-targeted-wake.txt", "r");
    if (f) { pes27_targeted = fgetc(f) == '1'; fclose(f); }
}
static const void *pes27_resolve(unsigned int handle, const void *thread)
{
    struct horizon_server_handle_entry *entry;
    if (handle == HORIZON_CURRENT_THREAD_HANDLE) return thread;
    entry = horizon_server_find_handle_locked(handle);
    if (!entry) return NULL;
    /* Files, timers and message queues can change without an explicit object
     * notification. Preserve their opportunistic rechecks on every signal. */
    switch (entry->object->type) {
    case HORIZON_SERVER_OBJECT_EVENT:
    case HORIZON_SERVER_OBJECT_MUTEX:
    case HORIZON_SERVER_OBJECT_SEMAPHORE:
    case HORIZON_SERVER_OBJECT_THREAD:
        return entry->object;
    default:
        return NULL; /* conservative broad interest */
    }
}
static void pes27_wake(void *condition)
{
    pthread_cond_signal(condition);
}
static void pes27_signal_object_locked(const void *object)
{
    /* Initialized on first sleep, before any private waiter can exist. */
    pes27_notify(&pes27_router, object, pes27_targeted, pes27_resolve,
                 pes27_targeted ? pes27_wake : NULL);
    if (!pes27_targeted && horizon_server_sleepers)
        pthread_cond_broadcast(&horizon_server_objects_cond);
}
static void horizon_server_signal_changed_locked(void)
{
    /* Unclassified changes (thread exit, abandoned mutexes, messages, I/O)
     * retain wake-all routing. Start gates also remain broad interests. */
    pes27_signal_object_locked(NULL);
}
static void pes27_sleep_locked(long long timeout, const struct pes27_interest *interest)
{
    static __thread pthread_cond_t private_cond = PTHREAD_COND_INITIALIZER;
    struct pes27_waiter waiter = { .interest = interest, .condition = &private_cond };
    pthread_cond_t *condition;
    pthread_once(&pes27_once, pes27_init);
    condition = pes27_targeted ? &private_cond : &horizon_server_objects_cond;
    if (timeout > HORIZON_SERVER_WAIT_SLICE) timeout = HORIZON_SERVER_WAIT_SLICE;
    pes27_register(&pes27_router, &waiter);
    ++horizon_server_sleepers;
    condvarWaitTimeout(&condition->cond, &horizon_server_objects_mutex.normal, (u64)timeout * 100);
    --horizon_server_sleepers;
    pes27_unregister(&pes27_router, &waiter);
}
static void horizon_server_sleep_locked(long long timeout)
{
    pes27_sleep_locked(timeout, NULL);
}
/* Do not hold the object lock across logging. Called only every ten seconds. */
void wine_nx_perf27_sync_snapshot(unsigned long long out[7])
{
    pthread_mutex_lock(&horizon_server_objects_mutex);
    out[0] = pes27_targeted;
    out[1] = pes27_router.notices; out[2] = pes27_router.broad_notices;
    out[3] = pes27_router.candidates; out[4] = pes27_router.notified;
    out[5] = pes27_router.filtered; out[6] = pes27_router.sleeps;
    pthread_mutex_unlock(&horizon_server_objects_mutex);
}
