# FEX3 self-suspend candidate

The `team-sync` device run regressed to a frozen intro, according to the tester.
It did not establish that full TSO fixes the earlier team-selection stall.
This update restores the previous Fastest configuration and fixes a concrete
missing thread operation in the native Horizon server. The tester now reports
passing intro/team selection and reaching a match at visually around 30 FPS,
with a few remaining bugs. No new timing log accompanies that report, so
stable measured FPS and repeated-run reliability are not established.
The exact tested artifacts are recorded in [FEX3-CHECKPOINT.md](FEX3-CHECKPOINT.md).

## Evidence

Input: `local/fex3/self-suspend/before/fex-runtime.log`, SHA-256
`9b955c0c0befac4497fe8876f2cff50dbf62e1732edfb46d99dbea3b2dfcb765`.

- The active build is `pes13-fex3-team-sync`, Fast, TSO 1/1/1.
- Presents reach 1,230 at 55 seconds and remain there at 60 seconds.
  The log ends before the first ten-second stall capture would be due;
  there are no `[FEX3-HANG-PC]` samples in this file.
- The last server-report interval records **375,126** self-suspend requests
  from thread 124 to itself. All return `c00000bb` (`STATUS_NOT_SUPPORTED`).
  Thread 72 makes another 7,132 rejected self requests in that interval.
- Worker 124 consumes 61.7% of one core, with its server worker at 28.1%.
  Its server traffic includes the matching duplicate/query/close requests
  made by Wine's ARM64 suspend wrapper. This is not successful suspension.
- Audio underruns rise from 9 to 1,566; no final crash or heap allocation
  failure is recorded. The log reports 590 MiB native heap free.

Those observations establish an unsupported self-suspend path and expensive
retry traffic. They do not prove that this is the only cause of the freeze,
or that enabling TSO caused the regression rather than changing its timing.

## Native server change

The previous `horizon_thread_suspend` rejected every already-started thread.
The isolated FEX runtime now distinguishes a **synchronous self request** by
object identity from a request to stop another running thread.

For a self request, the client is inside `wine_server_call`: it cannot execute
more game code until its own server connection replies. The server increments
the real suspend count and withholds that reply until another thread resumes
it to zero. It sleeps on the existing object condition variable, releasing
the server object mutex while asleep. This reuses the same mechanism as the
runtime's existing `CREATE_SUSPENDED` start gate, rather than using a timer
to emulate successful suspension.

The operation preserves prior counts, nesting, maximum-count errors and
terminated/invalid-handle errors. A different thread may add a count while
the target is already parked at this safe point. Suspending an arbitrary
running foreign thread remains unsupported. The connection owns a reference
to the parked object, so closing public handles cannot free it mid-wait.
Resume before suspend does not accumulate a future wake credit.

These count rules follow the documented
[SuspendThread](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-suspendthread)
and [ResumeThread](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-resumethread)
contracts. The condition-variable implementation is specific to this port.
Blocking intentionally until a matching resume is necessary for the API;
the change cannot repair an application that never issues that resume.

`[FEX3-SELF-WAIT]` reports aggregate entered/returned/waiting counts at the
existing progress cadence. There is no per-call SD write or injected sleep.
Server elapsed request time now includes legitimate parked time; it must
not be interpreted as CPU busy time. The bounded stall observer remains.

## Preset and unchanged components

The new package selects `fex_fast=1`, `fex_fastest=1`, matching `final-3d` before
the ordered-Fast experiment. The FEX DLL and ARM64 ntdll are byte-identical
to `team-sync`. RX tracking, native private heap, early 128 MiB spare JIT,
static-text checks, DXVK, graphics settings and the host ABI remain intact.
Fastest still relaxes scalar/SIMD/string ordering and is experimental.

Only the isolated FEX native server is changed; the Box64 build is not patched.
The original test delivery also included a rollback to `final-3d`, which
still hung at team selection. Old distributions and rollback packages were
removed from `dist/` at the user's request after the successful match report
and retained in a local archive. The current
packager produces only the latest version and does not require old ZIPs.

## Validation

- WSL builds the native NRO successfully; existing ABI-3 PE dependencies are
  preserved and their hashes are checked when packaging.
- The real patched server handlers and thread-state header pass ASan/UBSan
  tests with 1,000 actual concurrent pthread park/resume cycles. Tests also
  cover no reply before resume, spurious wakes, nested counts, overflow,
  resume-before-suspend, pseudo/alias handles, object identity and termination.
- The linked ARM64 suspend handler passes eight scenarios under Unicorn,
  including its real wire reply, safe-point flag and wait predicate. Kernel
  waits and pipe writes are modeled in that test.
- The paired native-heap/profile test passes against the final native ELF.
  Existing DLL and bounded-observer results are reused only where binary
  and/or source hashes are unchanged.
- None of these local checks establishes a Switch hang fix or measured FPS.

## Install and test

Close PES with HOME → X. Copy the complete `switch` folder from
`dist/pes13-fex3-self-suspend.zip` to the SD root and overwrite all four files:

```text
switch/pes13-fex/pes13-fex.nro
switch/pes13-fex/configuration.ini
switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll
switch/pes13-fex/drive_c/windows/system32/ntdll.dll
```

Keep the supplied INI (`run_guest_tests=0`, `fex_fastest=1`, `profile=0`).
Keep the same clocks and resolution for comparison. The log should identify
`pes13-fex3-self-suspend` and the Fastest profile.

Test intro → Exhibition → controller → team selection → kick-off.
If it freezes, leave it for **30 seconds** before closing via HOME → X,
then preserve `switch/pes13-fex/fex-runtime.log`. The diagnostic capture is
bounded to three bursts and does not need continuous profiling.
