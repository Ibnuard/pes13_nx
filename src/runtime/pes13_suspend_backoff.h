/* Experimental PES13 WoW64 wrapper, inserted into Wine's signal_arm64.c.
 * Keep native handle checks, suspend counts and status propagation. The
 * Horizon server refuses suspension of already-running threads. A caller
 * polling that refusal can otherwise occupy a core indefinitely.
 *
 * This changes scheduling, not suspension support. It is not an implementation
 * of running-thread suspension, and can delay callers that hold other locks.
 */
NTSTATUS WINAPI RtlWow64SuspendThread( HANDLE thread, ULONG *count )
{
    NTSTATUS status = NtSuspendThread( thread, count );

    if (status == STATUS_NOT_SUPPORTED)
    {
        LARGE_INTEGER delay;
        /* Negative NT time is relative, in 100 ns units: 1 ms. This runs
         * after the server has returned and released its object mutex.
         * Non-alertable sleep avoids dispatching APCs inside this wrapper. */
        delay.QuadPart = -10000;
        NtDelayExecution( FALSE, &delay );
    }
    return status;
}

