# FEX3 targeted synchronization and pacing

**Device result: regressed.** The tester reported heavier 3D and a complete
freeze before kick-off. Use [sync recovery](FEX3-SYNC-RECOVERY.md); the
selective router is no longer the default. The notes below describe the
original candidate and its pre-device-test rationale.

This candidate reduces unnecessary native server wakeups. It preserves the
FEX self-suspend checkpoint, Fastest profile, guest clocks, DXVK DLL and the
previous test's `maxFrameLatency=1` / `maxFrameRate=-1`. It is a runtime
optimization with local validation, not a verified fix for Switch pacing or
a claim of sustained 30 FPS at stock clocks.

## Device evidence

Input: `local/fex3/kickoff-result/fex-runtime.log`, 118,118 bytes,
SHA-256 `45f08a25cdc73dd48ad778e4afda7fc6ec529f48b694c5b2158f6d89361718b3`.
Reproduce the report with `tools/analyze-fex-sync-pacing.py LOG --output JSON`.

The tester reports a first-kick-off pause when the scoreboard appears, stock
clocks initially, and CPU-only OC after about three minutes. The scoreboard
clock remains stable while 3D motion feels doubled or jumpy. That distinction
supports investigating uneven frame delivery and catch-up rather than scaling
the global guest clock. It does not identify the exact animation algorithm.

The log contains long sections near 18–19 host presents/s and later sections
near 41–50. The sharpest jump is between approximately 231 and 241 seconds
after the first pacing report; no clock-change marker proves which interval
matches the approximate OC time. Presents do not count unique images.

The longest present-entry gap is 1,043,996 us. During slow match windows,
native present averages about 0.5–0.7 ms, acquire around 0.15 ms and driver
submit around 0.6 ms per call. These calls alone do not account for the roughly
53 ms between presents. Submit occasionally reaches 246 ms; other code and
scheduling before presentation remain relevant. Fence/semaphore durations
include intentional waits on concurrent threads and must not be summed into
a frame's CPU budget.

Wine's shared clock updates average around 1 ms with a longest recorded gap
of 8,005 us and no invalid sample. A seconds-long shared-clock update stall is
not present in this run. Native QPC uses converted 100 ns physical-counter
ticks and reports the matching 10 MHz frequency. CPU OC does not justify a
clock divisor or an artificial game-speed multiplier.

The 120-second server window ending near the 236-second progress report has
824,938 requests: 218,748 event operations, 177,991 mutex releases and 41,409
semaphore releases. Source audit finds that the FEX native base still broadcasts
every relevant object change to all waiting selects. The older Box64 PERF27
router was not included in this isolated FEX branch. Its previous device logs
filtered about 93–94% of candidate notification attempts, but that is neither
an FEX measurement nor an FPS speedup prediction.

## Change

Port the shared, tested object-identity router to FEX. A select waiting for an
event, mutex or semaphore now receives notifications for its dependencies.
Duplicate handles resolve to the same object; WAIT_ALL retains every dependency.
Closed/unknown handles and polling objects receive broad notifications.
Object acquisition, return status, signal-and-wait ordering, timeout arithmetic,
the 20 ms safety recheck and 1 ms message polling remain unchanged.

FEX's synchronous self-suspend and thread start gates retain the original
shared condition and broad wakeup path. Resume never depends on the private
select router. Thread exit, abandoned mutexes, messages, completion ports and
other unclassified changes still notify all waiters. Registration and removal
hold the existing object mutex around the atomic condition wait/unlock.

`[FEX3-SYNC]` reports filtered notification attempts every ten seconds.
`[FEX3-DELAY]` reports Sleep/yield counts and elapsed wall time by Wine thread,
including sleep overshoot and its lifetime peak. It observes the original
NtDelayExecution implementation; no sleep duration, clock, return value or
scheduling policy is modified. The observer uses fixed storage and does no
file I/O, allocation, new lock or thread suspension on the hot path.

## Install / comparison

Copy `dist/pes13-fex3-sync-pacing/switch` to the SD root after HOME -> X,
overwriting the supplied five files. Use the existing `pes13-fex.nro`
forwarder. This is a folder-only overlay, without a ZIP or game/save files.
The previous kick-off package and committed self-suspend checkpoint remain.

Check build `pes13-fex3-sync-pacing` and `[FEX3-SYNC] startup targeted=1`.
Test with a fixed clock setting for the whole run; test stock in a separate
fresh run. Include the first kick-off, scoreboard appearance, fast passes and
a set piece/replay, then another few minutes of ordinary play. Preserve the
log and note whether the scoreboard clock stays stable while motion jumps.

For a controlled comparison, change only `fex_targeted_wake=0` in
`switch/pes13-fex/configuration.ini`, close and restart. This uses the original
broadcast policy on the same NRO, retaining identical diagnostics, FEX,
graphics and DXVK queue settings. Restore `1` for the candidate. Do not change
DXVK latency or OC during the same comparison.

Local validation includes ASan/UBSan routing and delay tests, 16,000 generic
router handoffs and 18,000 FEX-adapter handoffs without rescue polling,
targeted/control and shared-gate wakeups, alias/closed handles, unchanged
server result functions, linked ARM64 routing and self-suspend checks, frame
and pipeline observers, FEX ABI/config/heap checks and package hashes.
Linux/model tests do not establish Horizon scheduling or match performance.
