/* LGPL-2.1-or-later. Snapshot self-suspended owners without changing any count.
 * Only called for a bounded hang capture, before pausing kernel threads. */
void wine_nx_fex_hang_waiters_report(void)
{
    extern void wine_nx_runtime_trace(const char *);
    struct { unsigned tid, suspend, terminated; } rows[64];
    struct fex_resume_waiter *waiter;
    unsigned n = 0, i;
    char line[160];
    pthread_mutex_lock(&horizon_server_objects_mutex);
    for (waiter = fex_resume_waiters; waiter && n < 64; waiter = waiter->next) {
        rows[n].tid = waiter->object->thread.tid;
        rows[n].suspend = waiter->object->thread.suspend;
        rows[n].terminated = waiter->object->thread.terminated;
        ++n;
    }
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    snprintf(line, sizeof(line), "[FEX3-HANG-WAITERS] self_suspended=%u limit=64", n);
    wine_nx_runtime_trace(line);
    for (i = 0; i < n; ++i) {
        snprintf(line, sizeof(line), "[FEX3-HANG-WAITER] tid=%u suspend=%u terminated=%u",
                 rows[i].tid, rows[i].suspend, rows[i].terminated);
        wine_nx_runtime_trace(line);
    }
}
