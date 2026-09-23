# PERF3 Wine-server bypass experiment

PERF2 made 2D rendering smooth and raised the match estimate to roughly 8-10
FPS, but the application continued to issue millions of thread-suspend calls.
At 180 seconds, four related operations accounted for about 19.3 million Wine
server requests: duplicate handle, query thread, close handle, and suspend.

PERF3 moves the compatibility fallback into ARM64 `RtlWow64SuspendThread`,
before that four-request sequence. Wine-NX/Horizon hosts the Windows threads
inside one process and has no safe asynchronous primitive for stopping an
already-running pthread. The custom function therefore returns success with a
previous suspend count of zero. `BOX64_DYNAREC_BIGBLOCK` remains `0` and the
persistent DXVK shader cache remains enabled.

The PERF3 NRO and `drive_c/windows/system32/ntdll.dll` are a matched pair. Close
PES from HOME, extract the overlay's `switch` directory to the SD root, and
overwrite both files. Keep the existing game, settings, saves and controller
profile. Use the same forwarder.

Confirm the log contains `pes13-nx-0.2.0-perf3-fast-suspend` and `[PERF3]`.
Test the same path through team selection, game plan, pre-match and at least
three minutes of the same match. Close through HOME and return
`switch/pes13-nx/pes13-nx.log`.

The expected result is that `dup_handle`, `get_thread_info`, `close_handle` and
`suspend_thread` no longer dominate the `[SERVER]` report. If boot or game state
regresses, extract `pes13-perf3-rollback.zip` to restore the original NRO,
Box64 profile and ARM64 ntdll.
