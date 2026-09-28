/* LGPL-2.1-or-later. Relative NT delays use elapsed monotonic 100ns ticks.
 * Included in sync.c after monotonic_counter and svcSleepThread declarations.
 * Do not convert a relative deadline to wall time, or yield while still ready
 * before blocking. The caller preserves alertable, infinite and zero waits. */
static NTSTATUS fex_relative_delay(ULONGLONG duration)
{
    const ULONGLONG begin = monotonic_counter();
    for (;;) {
        ULONGLONG elapsed = monotonic_counter() - begin;
        ULONGLONG remaining;
        if (elapsed >= duration) return STATUS_SUCCESS;
        remaining = duration - elapsed;
        /* Bound multiplication and recheck long waits at least hourly.
         * Early wakes retry against the original deadline, never start over. */
        if (remaining > 36000000000ULL) remaining = 36000000000ULL;
        svcSleepThread((int64_t)(remaining * 100));
    }
}
