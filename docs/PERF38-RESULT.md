# PERF38 first Switch result: optimization active, event slowdown remains

Input archived at `local/perf38/results/5438c8383572/pes13-nx.log`, SHA-256
`5438c83835726f0ab228d4435a1102edf898b7bc9e64bb27a0575f6ef129d6f5`.
This is one successful PERF38 run with the CPU sampler off, ending at about
250 seconds of application uptime. `tools/analyze-perf38-result.py` regenerates
the interval and lifecycle analysis.

| Window ending | Presents/s | Game worker | Worker CPU | Main CPU | Host present mean |
|---|---:|---|---:|---:|---:|
| 100 s | 29.45 | 176 | 50.6% | 69.4% | 0.59 ms |
| 110 s | 21.55 | 176 | 90.4% | 65.3% | 1.15 ms |
| 140–220 s | 18.41 weighted | 188 | about 89% | about 60% | mostly 0.8–1.4 ms |
| 240 s | 23.96 | 188 exited; 200 starting | 200 at 9.2% | 60.2% | 1.76 ms |
| 250 s | 18.28 | 200 | 46.4% | 58.6% | 4.92 ms |

Worker 124 stays around 76% from 140 seconds onward. The 188 worker exits
between the 230 and 240 reports; the new 200 worker starts at the same generic
guest entry (`0x4da0e3`). The higher present rate in the transition interval
and lower rate as the replacement becomes busy reproduce the user's report of
an initially smoother phase and slow motion after an event. The log has no
scene markers, so the exact goal/replay timestamp is user context, not a
machine-recorded transition.

The PERF38 guard fusion really compiled into the game: the report reaches 191
merged guards across 13 blocks, including 114 in guest block `0x113027b` and
28 in `0x112f8f0`. Yet sustained busy-worker intervals remain about 18.4
presents/s. Compilation counters do not measure executions or CPU cycles, so
this does not quantify the optimization's isolated FPS effect. The run has no
recorded fault and no 500 ms quiet frame gaps in the 140–220 s group. It is a
sustained frame-budget problem, with transitions layered on top.

The short host-present averages do not measure all DXVK/NVK work or GPU time.
`D3D9DeviceEx: Using extended constant set for software vertex processing` is
a DXVK capability message; it is not evidence that PES13 actually used CPU
software vertex processing. This run cannot justify changing the driver or
moving all 3D work to the GPU.

## Next evidence with the same NRO

Use the already built `dist/pes13-perf38-diagnostics-overlay.zip` on top of
the tested PERF38 package. It changes only `configuration.ini` and
`pes2013.wine-nx.txt`: CPU sampling becomes active, and two bounded math-block
captures can include 12,296 native bytes. The forwarder and NRO stay identical.
The decoder now accepts that full size and validates missing/duplicate chunks.

Test one run with the same teams, stadium, clocks and resolution. Keep playing
through a goal or replay and at least 60 seconds of the slow phase, then copy
the complete `pes13-nx.log` before another launch rotates it. The expected
markers are `[BUILD] pes13-nx-0.2.0-perf38-region-fusion`,
`CPU sampler=2s/10s at 20ms`, `[PROF]` worker samples, and
`[PERF17-BLOCK] slot=6` / `slot=7`. `tools/analyze-perf38-diagnostics.py`
summarizes each interval and preserves the two native/guest blocks. The
sampling run may have additional stutter; compare its quiet frame gaps with
the current quiet run, and use the sampled PCs to decide which code merits
rewriting.

Previous PERF37 sampling attributes the changing worker mostly to translated
PES code and samples guest blocks `0x113027b`/`0x112fb90` heavily, while worker
124's largest sample bucket is `0x93df30` (the copy routine). Those are from a
different NRO/run. The new same-NRO sample must confirm whether the same code
dominates **before and after** the event. The generic thread start address does
not identify the worker's actual function.

The Winlator/L4T comparison at 1280×720 makes a 30 FPS goal worth pursuing,
but the identical resolution alone does not establish identical CPU/driver
paths or clocks. The measured 18.41 presents/s period would need its mean
frame interval reduced from roughly 54.3 ms to at most 33.3 ms (about 39%) to
reach 30. A random preset change is unlikely to establish where that reduction
comes from; the worker PCs and native block sequence will direct the next
implementation.
