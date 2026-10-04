# HIGH live-freeze diagnostic candidate v1

The user confirms the end of the latest log is already frozen: pitch/gameplay
stopped after half time, spectators continued, then the app was closed manually
about ten seconds later. This reproduction did not force-close.

Evidence: `transition.log` SHA-256
`d06d44d3ce4bcd24aa7453c8d5cf384ca679702e515e453bdfd6b5a042f2db25`.
It ends at 409,218 ms since the trace began. The last 20 seconds contain about
59 successful presents per second, with no present errors. These are screen
presentations, not proof of gameplay simulation advancing at 59 FPS.

Seven native `memalign(4096, 5242880)` failures appear around 374,577 ms,
all on thread `5e8188`. That is about 35 seconds before log end. Aggregate free
heap is about 137 MiB at the end; this does not imply a contiguous 5 MiB block
exists. The old events have no caller, and there is no FEX STOP or scratch-arena
failure. Neither temporal proximity nor aggregate heap size proves those
failures caused the freeze. `crash.log` is armed but has no fatal record.

The prior no-frame stall probe cannot diagnose a freeze that still presents
spectators. Additionally, the delivered crash-v1 header had a zero native base
and unavailable build ID: `__start__` is an absolute-zero linker symbol on this
target. These gaps are the changes in this candidate, not new rendering or
memory-allocation policies.

## Changes

- `LIVE_TRACE_V1`: every six seconds, the existing maintenance worker captures
  CPU ticks and one native context for up to 128 registered Wine/server threads,
  even while Present continues. Rows include handle/TID, PC/LR/SP/FP, selected
  registers and results of the pause, read and resume calls.
- The existing profile mutex guards handle lifetime. Both locks are acquired
  with try-lock, and the registry lock is released before pausing. Self is
  excluded. A successful pause is immediately followed by one context read and
  resume, including on read failure. One failed resume gets one retry; another
  failure disables subsequent context captures. Unsupported SVC permissions
  leave CPU-tick observations available. No file I/O, allocations, sleeps,
  stack reads, foreign-memory reads or Wine/FEX helper calls happen while a
  thread is paused. Formatting and file I/O follow the completed snapshot.
- `ALLOC_SITE`: failures retain the native return address and errno alongside
  size/alignment/thread. Success paths do not collect this metadata, and errno
  and allocation semantics are preserved. The 32-entry failure ring uses a
  non-waiting guard and resets after a worker drain.
- `CRASH_V2`: resolve the actual code mapping with `svcQueryMemory` on the
  bootstrap function, then read the delivered NRO header there. Record the
  runtime base in `transition.log` too for offline symbolication. An unavailable
  mapping remains explicitly unavailable; no guessed build ID is emitted.

The snapshot contains registered threads only; it is not an OS-wide debugger.
Sampling can perturb scheduling. `capture_us` reports each snapshot duration;
console overhead and permission behavior remain unmeasured until the next test.
The existing opt-in two-second trace and its 600-sample limit remain. Turning
off `launcher/diagnostics.txt` turns off live snapshots too. Fatal capture still
uses the independent preopened file described in FEXTENDO-CRASH-LOG.md.

Scratch arena v2, the production FEX DLL, game timing, graphics preset, DXVK,
controller and keyboard behavior remain as in crash-v1. The runtime release
lock and experimental patch chain are not modified. The package is a folder
overlay with two install files and an exact crash-v1 NRO rollback. No ZIP.

## Validation and next reproduction

Host tests under ASan/UBSan cover bounded logging despite advancing frames,
allocation call sites/errno, mutex contention, immediate resume on read error,
resume retry/disable, CPU-tick fallback, and crash bootstrap mapping failure.
Tests execute the delivered ARM64 observer and crash bootstrap with modeled
libnx/FS/kernel services to check actual ABI layout and native return addresses.
Existing controller, keyboard, allocator and silent-boundary binary checks run
against the new ELF. Source checks verify unchanged Vulkan call arguments and
the original thread-profile implementation with only the observer appended.
Receipts and exact ELF/NRO hashes accompany the package.

These checks do not establish a fix, device pause overhead or gameplay FPS.
Use HIGH + Default DXVK and the same fixed clocks. Reproduce half-time,
ball-out and replay transitions. If gameplay freezes while the crowd moves,
allow about 15–20 seconds before HOME > X > Close. Collect `transition.log`
and `crash.log` before reopening. If already reopened once, include both
`.previous.log` files. The final LIVE rows will let us compare the blocked or
busy thread with the healthy interval, and allocation callers can be resolved
against the exact ELF rather than guessed from the failure size.
