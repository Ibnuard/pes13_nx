# PERF37: changing match cadence, with sampled native instructions

Input: `local/perf37/results/a03c22c64e05/pes13-nx.log`, 529,956 bytes,
SHA-256 `a03c22c64e051ea08a9d842b7e8a43ee53b0677658b722548d5599808e95c667`.
The filename was under the PERF34 directory, but the embedded build marker is
`pes13-nx-0.2.0-perf37-jit-probe`. This is the PERF37 diagnostic build, not PERF34.
The log covers approximately 391 seconds and contains 144 thread sampling
intervals with no dropped opcode/block histogram entries. No exception was
recorded in this submitted run.

The user observed slow motion, then smoother play after a replay/celebration,
then slow motion again after another event. The approximate event time supplied
was **after five minutes**. That is not enough to label an exact log interval
as gameplay or celebration.

| App uptime | Presents/second | Mean frame gap outside sampling | CPU core equivalents |
|---|---:|---:|---:|
| 301 s | 17.70 | 56.59 ms | 2.89 |
| 341 s | 19.56 | 51.26 ms | 2.88 |
| 351 s | 18.77 | 52.79 ms | 2.89 |
| 361 s | 29.84 | 35.07 ms | 2.04 |
| 371 s | 16.26 | 66.76 ms | 2.57 |
| 381 s | 16.85 | 56.21 ms | 2.03 |
| 391 s | 17.68 | 56.37 ms | 2.40 |

These are roughly ten-second intervals. Presents/second is not an independent
measurement of game simulation speed. Sampling affects timing; the quiet-gap
column excludes sampling epochs, but cannot remove every observer effect.

Worker 204 exits between the 351 s and 361 s reports. Worker 220 appears after
the 361 s report, later exits, and worker 232 appears after the 381 s report.
This correlates with the change in work, but does not prove thread creation,
scheduling, or the replay transition causes the slowdown. The generic guest
thread entry `0x4da0e3` is not a decoded simulation function.

## What the new probe establishes

Actual sampled ARM instructions include repeated FPCR reads/writes, guest
x87 control-word loads, float widening, and dispatch-table loads. Hot guest
blocks include `0x113027b` (1,113 guest bytes / 12,296 native bytes),
`0x112fb90` (656 / 7,064) and `0x112f8f0` (232 / 2,736). These are better
optimization targets than changing the graphics backend again without a
measured cause. `tools/report-perf37-result.py` produces exact per-thread-group
counts and timeline in the archived result directory.

The existing PERF20 pass discards a complete native block if it contains any
branch other than its final dispatcher. At the end of this run it reports
54,357 flow rejections, 71 changed blocks and 425 merged guards. These are
**compilation counts**, not execution counts. Its ten-word pattern also misses
the eleven-word x87 memory-operand form with float widening inside the guard.
PERF38 addresses these two restrictions in the measured math pages.

Large numbers of sampled loads do not establish RAM bandwidth saturation.
Wall samples include waiting and are not CPU-cycle shares. The small duration
of the host present call does not measure the complete GPU/driver workload.
No full GPU timestamp profile is available from this log.

At the last progress report, heap free space is about 496 MiB and invalidations
have increased only from 5,598 to 5,616 since the previous report. This log does
not demonstrate memory exhaustion or an invalidation storm. The cumulative
audio counter is not a count of audible stutters.

The gate which enables scoped FASTROUND after the first present can leave
earlier compiled blocks with the conservative preset, and the matrix page is
explicitly excluded from that override. This is a source-level explanation for
why rounding guards can remain; PERF37 does not record each block's creation
time/environment, so it does not prove which explanation applies to every
sampled block. PERF38 keeps the rounding behavior intact rather than forcing
a different global mode.
