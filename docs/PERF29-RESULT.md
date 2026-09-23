# PERF29: match-stall regression report, 2026-09-22

## Decision

Do not promote worker block growth. The user reports repeating/echoing audio
and repeated/stuttering frames during a match. The new run records a severe
presentation stall. Disable only PERF29 worker block growth for the next
hardware test; do not change audio latency, math policy, renderer or clocks
at the same time. This is a reversible mitigation/control, not a proven fix.

## Evidence identity

Only `pes13-nx.log` is new PERF29 evidence, SHA-256
`08265f028614ea2b1744e690e3806549271e0bdc9c92d97a00acd0bf4b3c7f20`.
It reports `pes13-nx-0.2.0-perf29-worker-blocks`, CPU sampler off in both
configuration reports, and active `worker_blocks=1`. The initial zero mode
line is emitted before initialization and must not override later reports.
The final compilation counts are selected=completed=4885, max_guest=8800,
max_native=36720. They establish activity, not correct execution or savings.

All four `previous-*` files are byte-identical to already archived PERF28
logs, shifted by one rotation. `previous-1` is the historical successful run;
`previous-2` through `previous-4` are historical startup failures. These are
not four further PERF29 tests and no same-NRO control run is supplied.

## Timings

Intervals use PERF8 uptime, not the separate PROGRESS clock. Scene boundaries
are not recorded; match context comes from the user's report.

| PERF8 window ending | Successful presents/s | Quiet gap mean | Host submit mean |
| --- | ---: | ---: | ---: |
| 90 s | 17.55 | 56.763 ms | 3.724 ms |
| 100 s | 14.49 | 65.177 ms | 0.983 ms |
| 110 s | 2.60 | 406.933 ms | 74.398 ms |
| 120 s | 2.00 | 500.916 ms | 58.899 ms |

The final two windows contain 46 presents over 20.014 seconds: 2.298/s.
Of 46 measured quiet gaps, 22 exceed 500 ms and seven exceed one second.
The launch-wide maximum gap is 1.845456 seconds; it occurred before those
last windows, so it is not their window-local maximum.

Host submit spans total 12.449362 seconds across 184 calls in those windows,
averaging 67.660 ms. The launch-wide submit maximum grows to 1.019795 seconds.
These spans measure wall time inside the host Vulkan submission calls, not
GPU execution time, and cannot be added to other overlapping thread spans.
Blocking/backpressure, scheduling and driver work remain possibilities.
The present-lock spans round to zero in both final windows; that particular
lock is not where the logged delay accumulates.

Historical PERF28 had approximately 18.91 presents/s in windows ending
110-150 s, and 15.34/s in windows ending 170-330 s. Those are not matched
scenes/clocks, and PERF28 sampling was on. They describe historical behavior,
not a controlled regression percentage.

## Audio and uncertainty

The sole new PROGRESS line has `audio_under=608` and appears after PERF8
uptime 120 s, although its own clock says 60 s. Do not place it at PERF8 60 s.
In `wine-nx-probe/source/audio_unix.c`, `nx_pump` increments this counter on
each pump observing `played != 0 && submitted == 0`. It does not require
pending producer frames and can count repeated observations of one empty
period. Thus 608 is not 608 distinct audible underruns or proof of echo.

The simultaneous user-visible symptoms are compatible with late audio/game
updates, but logs contain neither buffer contents nor per-interval producer
timing. They cannot distinguish stale audio replay from other audio defects,
nor establish that identical frame contents were presented. There is no
captured FAULT28/BOX64 fault in the new run; its ending does not prove a clean
exit. The recurring historical startup fault remains separate and unresolved.

## Control package and test

`dist/pes13-perf29-control-full.zip` contains the exact existing PERF29 NRO
and main-package runtime/config files, with only `perf29-worker-blocks.txt`
changed from `1` to `0`. CPU sampling remains off in both layers. The NRO
title/build marker stays PERF29. One NRO; no saves, game EXE or settings.dat.
This repack does not introduce a new runtime build or claim a hardware fix.

1. Close PES13-NX completely with HOME, X, Close.
2. Extract the full-control ZIP onto the SD root, overwriting its included
   files. Keep the forwarder and existing game/save folders unchanged.
   If PERF29 is already installed intact, the original small
   `pes13-perf29-control.zip` overlay has the same three control files.
3. Keep teams, stadium, resolution and clocks unchanged. Play the same match
   for 2-3 real minutes after kickoff, including a replay if practical.
4. Record whether audio repeats, whether frames stall, and whether play
   recovers after replay. Copy current and rotated logs before more launches.
5. Expect sampler off and `worker_blocks=0 ready=0 selected=0 completed=0`
   throughout the initialized control run. If stalls persist, block growth
   alone does not explain them; investigate host-submit waits and audio
   producer timing before attempting another optimization.

Do not use the sampling or PERF28 rollback package for this first comparison:
both also change sampling. Reinstalling the worker-blocks package re-enables
the suspect experiment and is not recommended for normal play yet.

## Reproduction and host validation

Raw copies and analysis are under `local/perf29/regression-20260922`, separate
from the older `local/perf29/results`. JSON records each input's hash and
byte-identical prior filename. Reproduce from the archived copies:

```
python tests/perf29_result.py
python tools/analyze-perf29-result.py local/perf29/regression-20260922/results --output local/perf29/regression-20260922/analysis.json
python tools/package-perf29-recovery.py
```

Parser tests cover mixed-build rotation, initialized modes, separate clocks,
weighted timing and histograms. Package checks cover pinned input archives,
all entry hashes, exact single-variable control, byte-identical NRO, embedded
metadata, single-NRO layout and ZIP integrity. None executes the Switch game.
