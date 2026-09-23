# PERF24 — bounded diagnosis on the smoother math-control baseline

This is a diagnostic build, not a verified FPS improvement or loading fix.
It retains PERF23's translator, scheduler, renderer, exception fixes and log
history. The package defaults to the user's tested math-control configuration:
scoped FASTROUND=1, X87DOUBLE=1, SAFEFLAGS=2. X87DOUBLE=0 is disabled.
No game executable, save, settings.dat or input mapping is changed.

## Install and collect one useful run

1. Before more launches, copy any existing `pes13-nx.previous-*.log` files from
   `switch/pes13-nx/` on the SD card. They may contain the loading failure that
   was overwritten by the subsequent successful current log.
2. HOME → X → Close. Extract `pes13-perf24-diagnostics.zip` to the SD root,
   overwrite, then use the existing forwarder to `switch/pes13-nx/pes13-nx.nro`.
3. Keep the same clocks and game settings. If loading sticks, wait about
   30 real seconds, then close/reopen normally. Continue into a match, through
   a foul or ball-out, and play for 30 real seconds after a sustained slowdown.
4. Copy `pes13-nx.log` **and all four available `pes13-nx.previous-*.log` files**
   before further launches replace them. Note the displayed match time at the
   event if possible. Do not erase shader caches or saves for this test.

The main ZIP contains one NRO. Its build tag is
`pes13-nx-0.2.0-perf24-diagnostics`. It resets profile=1 in both settings files,
verbose=0, perf22-floatmath=0, perf21-fastmath=1 and perf23-balance=1.

## Measurements

`[FRAME24]` gives successful-present completion gaps, separately during CPU
sampling (`gap_sampled`) and outside it (`gap_quiet`), plus host-present call
durations. Each report has ten histogram bins with upper limits in microseconds:
16667, 33334, 50000, 66667, 100000, 200000, 500000, 1000000, 2000000, infinity.
`max_since_launch_us` is cumulative, not the maximum only in that report.
Intervals that cross a sampling phase change are counted separately and
excluded from the two gap histograms. The first present on a thread has no gap.
Counter reads are concurrent, so report boundaries are approximate; counters
are monotonic and not reset. These are CPU-observed completions, not GPU
timestamps or counts of unique simulation frames. Host-present duration does
not include every renderer/driver operation or all lock waits.

The existing four-thread profiler now samples every 20 ms only during the last
two seconds of each ten-second wall-clock cycle. It remains off for the other
eight seconds. `[PROF]` identifies translated guest/native/system-call locations;
`[SAMPLE24]` records the number of sampling rounds and cumulative target-suspend
wall duration in the reporting interval. Suspend duration is not CPU time or a
full measure of profiler overhead. Samples include blocked time. Newly created
workers become targets at the next existing thread report; exiting workers may
lose the unreported samples attached to their slot. A missing hotspot is not
proof that the code was never busy. No SVC permission is added; if unavailable,
the profiler reports why it cannot start and frame metrics still work.

Frame hooks do no I/O, allocation or locking. Aggregates use the existing
10-second reporting and buffered 5-second SD flush. Sampling can still perturb
timing. It is intended to locate a bottleneck, not establish production FPS.
There is no forced frame limiter, timing hack, auto-restart or claimed 30 FPS lock.

## Controls and validation

`pes13-perf24-quiet.zip` disables only CPU sampling on the same NRO, retaining
frame metrics and math-control. Reapply the main ZIP to enable sampling again.
`pes13-perf24-rollback.zip` restores the exact PERF23 NRO with math-control,
sampling off and the same log-history behavior. Copy logs first.

Build with `tools/build-perf24.py` under WSL, no Docker. ASan/UBSan checks cover
histogram boundaries, sampling cadence, four concurrent writers and snapshot
totals. Existing scheduler, history, translation, exception and policy checks
remain enabled. Generated math sources must remain byte-identical to PERF22/23;
temporary source edits are restored. Package validation checks icon/NRO metadata,
ABI4 and DXVK identity, required config flags and ZIP contents. Hardware behavior
must still be tested on the Switch.
