/* LGPL-2.1-or-later. Observe native memory-properties queries, including
 * VK_EXT_memory_budget. No allocation, file I/O, or blocking producer lock.
 * This does not cache budgets or alter driver results. */
struct fex_memory_sample {
    uint64_t begin, end, wall_us, cpu_us;
    unsigned handle, cpu_valid;
};
struct fex_memory_batch {
    uint64_t calls, wall_us, cpu_us, cpu_valid_calls, peak_us;
    unsigned count;
    struct fex_memory_sample rows[32];
};
static pthread_mutex_t fex_memory_mutex = PTHREAD_MUTEX_INITIALIZER;
static struct fex_memory_batch fex_memory_batch;
static uint64_t fex_memory_dropped;

uint64_t wine_nx_fex_memory_begin(uint64_t *cpu)
{
    *cpu = UINT64_MAX;
    if (!fex_gap_probe_enabled) return 0;
    if (R_FAILED(svcGetInfo(cpu, InfoType_ThreadTickCount, threadGetCurHandle(), UINT64_MAX)))
        *cpu = UINT64_MAX;
    return armGetSystemTick();
}

void wine_nx_fex_memory_end(uint64_t begin, uint64_t cpu_begin)
{
    struct fex_memory_sample s = {0};
    uint64_t cpu = 0;
    if (!begin) return;
    s.end = armGetSystemTick();
    s.begin = begin;
    s.handle = threadGetCurHandle();
    s.cpu_valid = R_SUCCEEDED(svcGetInfo(&cpu, InfoType_ThreadTickCount, s.handle, UINT64_MAX))
                  && cpu_begin != UINT64_MAX && cpu >= cpu_begin;
    if (s.end < begin) return;
    s.wall_us = armTicksToNs(s.end - begin) / 1000;
    if (s.cpu_valid) s.cpu_us = armTicksToNs(cpu - cpu_begin) / 1000;
    if (s.cpu_us > s.wall_us + 1000) s.cpu_valid = 0;
    if (pthread_mutex_trylock(&fex_memory_mutex)) {
        __atomic_add_fetch(&fex_memory_dropped, 1, __ATOMIC_RELAXED);
        return;
    }
    fex_memory_batch.calls++;
    fex_memory_batch.wall_us += s.wall_us;
    if (s.wall_us > fex_memory_batch.peak_us) fex_memory_batch.peak_us = s.wall_us;
    if (s.cpu_valid) {
        fex_memory_batch.cpu_valid_calls++;
        fex_memory_batch.cpu_us += s.cpu_us;
    }
    if (s.wall_us >= 1000) {
        if (fex_memory_batch.count < 32) fex_memory_batch.rows[fex_memory_batch.count++] = s;
        else __atomic_add_fetch(&fex_memory_dropped, 1, __ATOMIC_RELAXED);
    }
    pthread_mutex_unlock(&fex_memory_mutex);
}

static void fex_memory_report(void)
{
    struct fex_memory_batch b;
    uint64_t dropped;
    if (!fex_gap_probe_enabled || pthread_mutex_trylock(&fex_memory_mutex)) return;
    b = fex_memory_batch;
    memset(&fex_memory_batch, 0, sizeof(fex_memory_batch));
    pthread_mutex_unlock(&fex_memory_mutex);
    dropped = __atomic_exchange_n(&fex_memory_dropped, 0, __ATOMIC_RELAXED);
    if (b.calls || dropped)
        log_line("[FEX3-MEMQUERY] calls=%llu wall_us=%llu cpu_us=%llu cpu_valid_calls=%llu peak_us=%llu recorded=%u dropped=%llu",
                 (unsigned long long)b.calls, (unsigned long long)b.wall_us,
                 (unsigned long long)b.cpu_us, (unsigned long long)b.cpu_valid_calls,
                 (unsigned long long)b.peak_us, b.count, (unsigned long long)dropped);
    for (unsigned i = 0; i < b.count; ++i) {
        const struct fex_memory_sample *s = &b.rows[i];
        log_line("[FEX3-MEMQUERY] begin_tick=%llu end_tick=%llu handle=%u wall_us=%llu cpu_valid=%u thread_cpu_us=%llu",
                 (unsigned long long)s->begin, (unsigned long long)s->end, s->handle,
                 (unsigned long long)s->wall_us, s->cpu_valid, (unsigned long long)s->cpu_us);
    }
}
