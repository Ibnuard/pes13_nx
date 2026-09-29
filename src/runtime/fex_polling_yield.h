/* LGPL-2.1-or-later. Reuse the monotonic samples for backoff and diagnostics.
 * Included in sync.c with the original yield policy; no timer scaling,
 * syscall/APC bypass, extra sleep, native callback or guest-memory caching.
 */
extern int wine_nx_fex_polling;
extern void wine_nx_fex_delay_zero_note(unsigned tid, uint64_t elapsed_us);

static NTSTATUS fex_poll_yield(uint64_t *elapsed_us)
{
    static __thread struct fex_yield_burst burst;
    if (!wine_nx_fex_yield_backoff && !elapsed_us) {
        svcSleepThread(0);
        return STATUS_SUCCESS;
    }
    const ULONGLONG begin = monotonic_counter();
    svcSleepThread(0);
    ULONGLONG end = monotonic_counter();
    if (wine_nx_fex_yield_backoff && fex_yield_pause_due(&burst, begin, end)) {
        const ULONGLONG pause_begin = end;
        svcSleepThread(50000);
        end = monotonic_counter();
        TEB *teb = NtCurrentTeb();
        if (teb) wine_nx_fex_yield_pause_note((unsigned)(ULONG_PTR)teb->ClientId.UniqueThread,
                                            end >= pause_begin ? (end - pause_begin) / 10 : 0);
    }
    if (elapsed_us) *elapsed_us = end >= begin ? (end - begin) / 10 : 0;
    return STATUS_SUCCESS;
}
