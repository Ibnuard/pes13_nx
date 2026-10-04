# Direct fatal evidence for the HIGH diagnostic candidate

Update: the live-freeze candidate uses recorder v2. The v1 console report
revealed that passing `__start__` yields zero on this target, so its build ID
was unavailable. V2 resolves the live text mapping through `svcQueryMemory`
before reading the NRO header. The actual bootstrap is now covered by the
ARM64 test, including this query, rather than testing only a supplied pointer.
The transition marker is `CRASH_V2`. Fatal record semantics below are unchanged;
see FEXTENDO-HIGH-LIVE-FREEZE.md for continuous-present thread observations.

The last arena-v2 `transition.log` (SHA-256
`953649dd49d4079a82cfbc9a7c50f35d4a46b812cb9fd6455c2d7e73c85bfcde`)
ends at 167,572 ms with presentation still progressing and no retained fatal
events. The user reports a subsequent Switch error dialog and automatic app
closure. This does not identify a crash cause. A two-second diagnostic worker
can lose the last event if the process terminates before the next sample.

This candidate adds `switch/pes13-fex/crash.log` while preserving arena v2.
It does not change the FEX DLL, game timing, graphics, input or memory policy.
The frozen native exception entry/slot allocator is unchanged.

## Persistence and scope

Before launching guest threads, rotate the existing file to
`crash.previous.log`, then open a native `FsFile` and preallocate/write 18 KiB.
If rotation fails, do not truncate the existing report. The header contains
the NRO's build ID, native load base and monotonic session tick, so neither
Windows timestamps nor the console's calendar are needed to identify it.
The `CRASH_V1` transition header includes the same session tick and the
transition clock origin. There is one previous report, not an unlimited history.

Eight fixed 2-KiB record slots capture these paths:

- An unhandled native exception, only after Wine's normal memory and guest
  exception recovery has failed. Capture status, PC/LR/SP/FP/FAR/ESR, GPRs,
  loaded FEX module address, preset, renderer and elapsed time.
- A FEX `STOP` message, before the diagnostic ring/worker. Routine logs and
  recoverable allocation/cache failure messages do not write this file.
- Nonzero guest exit before registry flushing.
- Linker wrappers for `abort`, `diagAbortWithResult` and `svcBreak`, preserving
  their original calls/arguments/results. Debug-notification breaks are ignored.

Each record makes one direct `fsFileWrite(..., FsWriteOption_Flush)` to the
preopened file. This bypasses stdio and the project's read-cache wrapper.
There is no allocation, printf-family formatting, stack walk, or waiting for
the recorder's own lock. Reentry/contention drops a record instead of spinning;
the first eight accepted records are retained. Record buffers are static and
bounded, with control characters sanitized in message text. Native FS IPC can
still fail or block; the logger cannot promise durability for every crash.

No crash-file writes occur during ordinary frames/polls. Only startup writes
and captured failure paths use this sink. Existing opt-in transition tracing
continues separately. Removing `launcher/diagnostics.txt` disables that worker's
trace, not this candidate's fatal sink. Rollback restores the prior arena-v2 NRO.

`Status=armed` without `RECORD=` means only that no failure record was captured.
It is not a clean-exit assertion. A direct kernel termination, power loss,
invalid/absent exception stack or exhaustion of the frozen exception slots
can bypass these hooks. Filesystem failure can prevent persistence. A logical
game freeze without an exception still needs `transition.log`. Atmosphere's
system report remains a fallback for failures outside the application handler.

The report uses hexadecimal numeric fields. The FEX DLL remains SHA-256
`17dcf3e78371a717a9c41da5bffa4d6a5755d6479afa0a8ade12abcc7639ad23`.
The NRO and matching companion ELF hashes are recorded in the build receipt;
symbolication must use that exact binary, not a previous build's offsets.

## Validation

Host tests exercise synchronous flush without a worker, fixed capacity,
full register capture, routine-log silence, restart rotation, failed rotation,
failed create/open/write, concurrent and reentrant failures, and preservation
of termination calls. They run with ASan/UBSan. ARM64 tests execute the actual
linked fatal callback/wrappers with FS/thread/termination services modeled,
including the real exception dump layout and delivered NRO build ID. Unknown
heap/stdio/locking calls fail the binary test. Source integrity verifies the
fatal hook is downstream of exception recovery and Vulkan call arguments are
unchanged. These tests do not reproduce a real console crash, an SD-controller
failure or PES gameplay. Device validation is still required.

For a reproduction, install the two-file overlay, use HIGH + Default DXVK and
fixed clocks, and collect `crash.log` together with `transition.log` before
relaunch. If already relaunched once, include both `.previous.log` files.
