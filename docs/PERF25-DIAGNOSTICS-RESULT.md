# PERF25 sampled console result

The new 200,925-byte log is archived in
`local/perf26/diagnostic-results/pes13-nx.log`. Reproduce the summary with
`python tools/analyze-perf25-diagnostics.py`. The four previous logs repeat
the prior upload; only the current file is new sampled PERF25 data.
The reported clock baseline remains CPU 1728 / GPU 768 / RAM 1600 MHz.

| Report windows ending | Presents/s, weighted | Quiet frame gap mean |
| --- | ---: | ---: |
| 40–60 s | 57.82 | 17.20 ms |
| 130–160 s | 16.00 | 60.72 ms |
| 170–210 s | 13.84 | 70.95 ms |
| 220–230 s | 17.63 | 57.01 ms |

In the slower interval, 78 of 555 quiet gaps exceed 100 ms, including four
over 200 ms. The 210-second report reaches 11.18 presents/s; the final two
reports recover to 17.18 and 18.08. This still falls well short of a 30 Hz
frame budget. These counters measure successful presents, not unique game
frames or simulation speed. There are no synchronized replay/goal/foul markers,
so they cannot establish the timing or cause of the reported persistent slowdown.

The 3D-period worker 176 uses 89.3–92.3% of one CPU core. Its sampled wall
time is 87.7% translated x86, with 3% native code and 9% system calls.
Worker 124 uses 76.2–81.7% of a core, with 77.7% translated x86 and 21.8%
system calls. The hot copy bucket at EXE+0x53df40 still accounts for 8.75%
of that worker's reported samples. Sampling includes blocked time and the
rounded top-site lists are incomplete; these are not exact running-CPU shares.
The hot work is spread through game code, not concentrated in a single driver
function. Host present averages about 0.43 ms in the last two windows, but
this does not measure all driver work or GPU execution.

Captured small routines at 0x93b85f and 0x93cfb0 call through to 0x9379f0.
The latter's return goes through an indirect jump-table lookup. This supports
testing Box64's existing guarded native call/return path as a broader CPU
optimization candidate. It does not prove return dispatch is the dominant
cost or predict a particular FPS gain. See PERF26.md for the isolated test.

This log has no new unhandled fault or exit. Worker 176 exits and replacement
workers 188 and 200 appear around later transitions. Without event labels,
their lifecycle cannot be assigned specifically to replay, goal or foul.

PERF25 pair-copy was compiled and accepted. Captured code includes both the
eight-byte-aligned pair path and the scalar fallback; this log does not count
which alignment path actually executes. No runtime-alignment claim is made.
