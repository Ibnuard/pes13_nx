/* LGPL-2.1-or-later. Included in the isolated Horizon server after the suspend
 * observer. A synchronous self request is already at a safe point: its guest
 * thread cannot leave wine_server_call until this connection writes a reply.
 * Use the existing start-gate wait, releasing the object mutex while asleep.
 * Do not pretend to stop a different running thread or inject a timed delay. */
static unsigned int fex_thread_begin_suspend(struct horizon_thread_state *thread,
                                              int self, int *previous)
{
    *previous = thread->suspend;
    if (thread->terminated) return HORIZON_THREADS_STATUS_ACCESS_DENIED;
    if (thread->started && !self && !thread->self_suspended)
        return HORIZON_THREADS_STATUS_NOT_SUPPORTED;
    if (thread->suspend >= HORIZON_THREAD_MAX_SUSPEND)
        return HORIZON_THREADS_STATUS_SUSPEND_EXCEEDED;
    ++thread->suspend;
    if (self && thread->started) thread->self_suspended = 1;
    return 0;
}

/* Protected by horizon_server_objects_mutex; reporting never runs per call. */
static uint64_t fex_self_suspend_waits, fex_self_suspend_returns;

static int __attribute__((noinline)) horizon_server_handle_suspend_thread(
    struct horizon_server_connection *connection, const unsigned char *message)
{
    const struct horizon_suspend_thread_request *request = (const void *)message;
    struct horizon_suspend_thread_reply reply = {0};
    struct horizon_server_object *object;
    unsigned int status, tid = 0;

    pthread_mutex_lock(&horizon_server_objects_mutex);
    if ((object = horizon_server_get_thread_locked(request->handle, &status)))
    {
        const int self = object == connection->thread;
        status = fex_thread_begin_suspend(&object->thread, self, &reply.count);
        tid = object->thread.tid;
        fex_suspend_observe(connection->tid, tid, status,
                            object->thread.started, object->thread.terminated);
        if (!status && self && object->thread.started)
        {
            ++fex_self_suspend_waits;
            /* The connection owns an object reference for this entire call,
             * even if another thread closes every public handle. Resume and
             * predicate checks share this mutex: there is no lost wake gap.
             * Another suspend can add a count while this safe point is held. */
            while (object->thread.suspend && !object->thread.terminated)
                horizon_server_sleep_locked(HORIZON_SERVER_WAIT_SLICE);
            object->thread.self_suspended = 0;
            ++fex_self_suspend_returns;
            if (object->thread.terminated) status = HORIZON_THREADS_STATUS_ACCESS_DENIED;
        }
    }
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    if (status == HORIZON_THREADS_STATUS_NOT_SUPPORTED)
        horizon_trace("[server] suspend_thread tid=%u refused: remote thread running", tid);
    reply.header.error = status;
    /* Reply only after resume, preserving the count from before suspension.
     * wait_handle remains zero: this uses no asynchronous context request. */
    return horizon_server_write_reply(connection->reply_fd, &reply, sizeof(reply), NULL, 0);
}

void wine_nx_fex_self_suspend_report(void)
{
    static uint64_t reported_waits, reported_returns;
    uint64_t waits, returns;
    char line[192];
    pthread_mutex_lock(&horizon_server_objects_mutex);
    waits = fex_self_suspend_waits;
    returns = fex_self_suspend_returns;
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    if (waits == reported_waits && returns == reported_returns) return;
    snprintf(line, sizeof(line),
             "[FEX3-SELF-WAIT] total=%llu returned=%llu waiting=%llu",
             (unsigned long long)waits, (unsigned long long)returns,
             (unsigned long long)(waits - returns));
    wine_nx_runtime_trace(line);
    reported_waits = waits;
    reported_returns = returns;
}
