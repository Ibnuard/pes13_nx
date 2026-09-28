/* Included after Horizon's server object definitions. These counters describe
 * real results, without changing suspension or introducing per-call I/O.
 * All updates/copies hold the server object mutex already used by suspend. */
struct fex_suspend_row {
    unsigned caller, target, status, started, terminated;
    uint64_t calls, rejected, succeeded, reported_calls, reported_rejected, reported_succeeded;
};
static struct fex_suspend_row fex_suspend_rows[32];

static void fex_suspend_observe(unsigned caller, unsigned target, unsigned status,
                                unsigned started, unsigned terminated)
{
    unsigned i;
    for (i = 0; i < 32; ++i) {
        struct fex_suspend_row *row = &fex_suspend_rows[i];
        if (row->calls && (row->caller != caller || row->target != target)) continue;
        row->caller = caller;
        row->target = target;
        row->status = status;
        row->started = started;
        row->terminated = terminated;
        ++row->calls;
        if (status == HORIZON_THREADS_STATUS_NOT_SUPPORTED) ++row->rejected;
        if (!status) ++row->succeeded;
        break;
    }
}

void wine_nx_fex_suspend_report(void)
{
    struct fex_suspend_row copy[32];
    unsigned i, n = 0;
    char line[256];
    pthread_mutex_lock(&horizon_server_objects_mutex);
    for (i = 0; i < 32; ++i) {
        struct fex_suspend_row *row = &fex_suspend_rows[i];
        if (row->calls == row->reported_calls) continue;
        copy[n] = *row;
        copy[n].calls -= row->reported_calls;
        copy[n].rejected -= row->reported_rejected;
        copy[n].succeeded -= row->reported_succeeded;
        ++n;
        row->reported_calls = row->calls;
        row->reported_rejected = row->rejected;
        row->reported_succeeded = row->succeeded;
    }
    pthread_mutex_unlock(&horizon_server_objects_mutex);
    for (i = 0; i < n; ++i) {
        const struct fex_suspend_row *row = &copy[i];
        snprintf(line, sizeof(line),
                 "[FEX3-SUSPEND-RESULT] caller=%u target=%u calls=%llu rejected=%llu succeeded=%llu last=%08x started=%u terminated=%u",
                 row->caller, row->target, (unsigned long long)row->calls,
                 (unsigned long long)row->rejected, (unsigned long long)row->succeeded,
                 row->status, row->started, row->terminated);
        wine_nx_runtime_trace(line);
    }
}
