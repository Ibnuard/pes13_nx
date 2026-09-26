/* LGPL-2.1-or-later. Only the diagnostics thread enters a metrics batch.
 * Fault/exit records still flush immediately. Other threads cannot inherit
 * this TLS state, so a concurrent bring-up failure is not buffered. */
static __thread int fex_log_metrics_batch;

static int fex_log_should_flush(const char *line, int running, int urgent)
{
    return !running || urgent ||
           (!fex_log_metrics_batch && !strncmp(line, "[FEX", 4));
}
