# PERF35 log and build audit — 2026-09-23

The user confirmed that the second run followed HOME → X → Close, not a second
match in one process. The five supplied logs were archived without modification
under `local/perf35/results/f8d84893a266/`; parsed records are in `analysis.json`.
Only the current log contains gameplay, so this set cannot quantify a regression
between two successful launches.

| Log | Observed outcome |
| --- | --- |
| current | Successful gameplay; about 260 seconds captured |
| previous-1 | Pre-runtime PES image mapping conflict |
| previous-2/3/4 | Startup guest fault at x86 `0x0115c36f`, null + 4 read, exit `0xc0000005` |

Zero presents after those faults belong to an exited/parked process. They are
not evidence of CPU saturation in an actively loading game. The crash and image
mapping issues remain unresolved by this performance experiment.

In the current log, report windows ending at 140–220 seconds average **13.303
presents/s**. Quiet present gaps average **75.188 ms** across 1,199 intervals;
1,047 (87.3%) fall in the 66.7–100 ms bin. No gap exceeds 200 ms in those windows.
This is primarily sustained low cadence in that part of the run. Scene/event
timestamps are unavailable and present rate is not a measurement of simulation
speed or unique displayed frames.

Host-present calls average 0.343 ms there. That only times the instrumented
present call, not all driver, DXVK, synchronization or GPU work. Guest worker
176 occupies about 90% of a core, worker 124 about 76%, with 2.65–2.81 cores
occupied in total. The PC sampler was disabled, so these logs do not identify
the exact current hot instructions. A warm cache loads 459 shaders. Heap free
remains about 507 MB at 240 seconds; exhaustion is not demonstrated.

The report windows at 230–250 seconds average 18.604 presents/s and include
some longer gaps; worker 176 exits and worker 188 appears. Without event
timestamps this does not prove a replay or corner caused a lasting slowdown.

## Correction to the PERF35 optimization claim

PERF34 and PERF35 generated dispatch sources both hash to
`5e015c2064468962d0db3f4e9f7490a2bb2950e3d8ce58dcada9fdbedf649557`.
Their dynablock sources both hash to
`cb94677534ac1cabd64fd39e4d94ae0d0c34d961acc5b83accccbfe1c21efd33`.
Both Ninja recipes omit `SAVE_MEM`; the dispatch object also compares equal.
The inherited PERF8 recipe had already removed the counters and SAVE_MEM.
The asserted new PERF35 dispatch improvement was incorrect.

## Actual new finding

PERF33 creates a per-block environment with `FASTNAN=1`, but eight ARM64 opcode
emitters still read `BOX64ENV(dynarec_fastnan)` (global 0), ignoring that override.
FASTROUND and X87DOUBLE had already been wired to per-block reads; FASTNAN had
not. PERF36 changes only those emitter reads to `BOX64DRENV`. Existing PERF33
scope, startup gates, SAFEFLAGS=2, X87DOUBLE=1, scheduler and current DXVK remain.

At 75 ms per present, a 33.3 ms target needs about a 56% reduction in the critical
interval. A limiter cannot supply that reduction. PERF36 has a testable CPU
mechanism but does not establish a 30 FPS result before hardware measurement.
