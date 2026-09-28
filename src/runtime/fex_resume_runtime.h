/* LGPL-2.1-or-later. FEX3 isolated synchronous self-suspend gate.
 * Pasted after fex_sync_horizon.h; no thread/object ABI changes. Every list,
 * predicate and counter access holds horizon_server_objects_mutex. A parked
 * connection owns its object reference until its handler returns. Waiters and
 * private conditions live on that handler's stack, never in handle storage.
 * This does NOT enable the optional select notification router. */
struct fex_resume_waiter {
    struct fex_resume_waiter *next;
    struct horizon_server_object *object;
    pthread_cond_t condition;
};
static struct fex_resume_waiter *fex_resume_waiters;
static struct {
    uint64_t waits, returns, rechecks, wakes, term_wakes, final, start, ignored, active;
} fex_resume_counts;

static void fex_resume_wake_locked(struct horizon_server_object *object, int terminated)
{
    struct fex_resume_waiter *waiter;
    for (waiter = fex_resume_waiters; waiter; waiter = waiter->next) {
        if (waiter->object != object) continue;
        pthread_cond_signal(&waiter->condition);
        ++fex_resume_counts.wakes;
        if (terminated) ++fex_resume_counts.term_wakes;
    }
}

static void fex_resume_wait_locked(struct horizon_server_object *object)
{
    struct fex_resume_waiter waiter = {
        .next = fex_resume_waiters, .object = object,
        .condition = PTHREAD_COND_INITIALIZER
    };
    struct fex_resume_waiter **link;
    fex_resume_waiters = &waiter;
    ++fex_resume_counts.active;
    while (object->thread.suspend && !object->thread.terminated) {
        ++fex_resume_counts.waits;
        /* Same libnx relative boundary as fex_sync_select_sleep_locked. Never
         * pthread_cond_timedwait: newlib realtime may be unavailable at boot.
         * Publication and atomic mutex release share the resumer's mutex. */
        condvarWaitTimeout(&waiter.condition.cond, &horizon_server_objects_mutex.normal,
                           (u64)HORIZON_SERVER_WAIT_SLICE * 100);
        ++fex_resume_counts.returns;
        if (object->thread.suspend && !object->thread.terminated)
            ++fex_resume_counts.rechecks;
    }
    for (link = &fex_resume_waiters; *link != &waiter; link = &(*link)->next) {}
    *link = waiter.next;
    --fex_resume_counts.active;
    pthread_cond_destroy(&waiter.condition);
}

/* Called only by the existing coarse log flusher, never by a suspend/resume.
 * waits/returns count condvar entries/exits; rechecks count still-held exits
 * (timeout or spurious). wakes count explicit signals, not scheduler wakeups.
 * Values cumulative so reports remain useful across sparse/idle intervals. */
void wine_nx_fex_resume_report(void)
{
    extern void wine_nx_runtime_trace(const char *);
    static uint64_t previous[9];
    static int reported;
    uint64_t now[9];
    char line[384];
    pthread_mutex_lock(&horizon_server_objects_mutex);
    now[0] = fex_resume_counts.waits; now[1] = fex_resume_counts.returns;
    now[2] = fex_resume_counts.rechecks; now[3] = fex_resume_counts.wakes;
    now[4] = fex_resume_counts.term_wakes; now[5] = fex_resume_counts.final;
    now[6] = fex_resume_counts.start; now[7] = fex_resume_counts.ignored;
    now[8] = fex_resume_counts.active;
    if (reported && !memcmp(previous, now, sizeof(now))) {
        pthread_mutex_unlock(&horizon_server_objects_mutex);
        return;
    }
    memcpy(previous, now, sizeof(now));
    reported = 1;
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    snprintf(line, sizeof(line),
             "[FEX3-RESUME] waits=%llu returns=%llu rechecks=%llu wakes=%llu term=%llu final=%llu start=%llu ignored=%llu active=%llu",
             (unsigned long long)now[0], (unsigned long long)now[1],
             (unsigned long long)now[2], (unsigned long long)now[3],
             (unsigned long long)now[4], (unsigned long long)now[5],
             (unsigned long long)now[6], (unsigned long long)now[7],
             (unsigned long long)now[8]);
    wine_nx_runtime_trace(line);
}
