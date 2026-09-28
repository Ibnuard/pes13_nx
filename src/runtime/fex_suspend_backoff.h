/* Match the working Box64 bridge: return the kernel/server's actual result.
 * An unconditional 1 ms sleep on every rejected request delays the caller,
 * even when the game handles NOT_SUPPORTED without retrying. The device log
 * records 10k-12k suspend requests per 10-second 3D window. Do not fabricate
 * successful suspension, modify the count on failure, or impose a frame-time
 * penalty here. The isolated server handles cooperative self-suspension;
 * asynchronous suspension of a different running thread remains unsupported. */
static NTSTATUS pes13_fex_suspend_local_thread( HANDLE thread, ULONG *count )
{
    return pWow64SuspendLocalThread( thread, count );
}
