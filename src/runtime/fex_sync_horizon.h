/* LGPL-2.1-or-later. FEX adaptation of the Box64 PERF27 notification router.
 * Called only with the existing server object mutex held. Object acquisition,
 * wait results and deadlines remain owned by the original Horizon server. */
#include "pes13_perf27_wait.h"
extern int wine_nx_fex_targeted_wake; /* immutable after single-threaded startup */
static struct pes27_router fex_sync_router;
static struct horizon_server_handle_entry *horizon_server_find_handle_locked(unsigned int);
static void horizon_server_sleep_locked(long long timeout);

static const void *fex_sync_resolve(unsigned int handle, const void *thread)
{
    struct horizon_server_handle_entry *entry;
    if (handle == HORIZON_CURRENT_THREAD_HANDLE) return thread;
    entry = horizon_server_find_handle_locked(handle);
    if (!entry) return NULL;
    switch (entry->object->type) {
    case HORIZON_SERVER_OBJECT_EVENT:
    case HORIZON_SERVER_OBJECT_MUTEX:
    case HORIZON_SERVER_OBJECT_SEMAPHORE:
    case HORIZON_SERVER_OBJECT_THREAD:
        return entry->object;
    default:
        /* Files, timers and message queues can change without a targeted
         * notification. Preserve their broad rechecks and polling cadence. */
        return NULL;
    }
}

static void fex_sync_wake(void *condition) { pthread_cond_signal(condition); }

static void fex_sync_signal_object_locked(const void *object)
{
    /* The recovery/control path must be the original shared broadcast,
     * including its cost: no list walk, handle resolution or router counters. */
    if (wine_nx_fex_targeted_wake)
        pes27_notify(&fex_sync_router, object, 1, fex_sync_resolve, fex_sync_wake);
    /* Start gates and synchronous self-suspend continue using the original
     * shared condition. Never filter their wakeups, including ResumeThread. */
    if (horizon_server_sleepers) pthread_cond_broadcast(&horizon_server_objects_cond);
}

static void horizon_server_signal_changed_locked(void)
{
    fex_sync_signal_object_locked(NULL);
}

static void fex_sync_select_sleep_locked(long long timeout, const struct pes27_interest *interest)
{
    static __thread pthread_cond_t private_cond = PTHREAD_COND_INITIALIZER;
    struct pes27_waiter waiter = {.interest = interest, .condition = &private_cond};
    if (!wine_nx_fex_targeted_wake) {
        horizon_server_sleep_locked(timeout);
        return;
    }
    if (timeout > HORIZON_SERVER_WAIT_SLICE) timeout = HORIZON_SERVER_WAIT_SLICE;
    pes27_register(&fex_sync_router, &waiter);
    condvarWaitTimeout(&private_cond.cond, &horizon_server_objects_mutex.normal, (u64)timeout * 100);
    pes27_unregister(&fex_sync_router, &waiter);
}

void wine_nx_fex_sync_snapshot(uint64_t out[7])
{
    pthread_mutex_lock(&horizon_server_objects_mutex);
    out[0] = wine_nx_fex_targeted_wake;
    out[1] = fex_sync_router.notices; out[2] = fex_sync_router.broad_notices;
    out[3] = fex_sync_router.candidates; out[4] = fex_sync_router.notified;
    out[5] = fex_sync_router.filtered; out[6] = fex_sync_router.sleeps;
    pthread_mutex_unlock(&horizon_server_objects_mutex);
}
