# PERF43 match probe: faster phases, but no sustained 30 FPS yet

Input: `C:/Users/Administrator/Pictures/pesnx/pes13-nx.log`, SHA-256
`42a121a410ced06c45f66eb67413981b0492e4c71ceffa470db9572d82f2e8e2`.
The embedded build is `pes13-nx-0.2.0-perf43-match-probe`; the profiler samples
for two seconds of each ten-second cycle. The tester reports kickoff at about
two minutes after application launch. Clock values were not supplied for this
run, so this log does not establish stock-clock performance.

| Window endpoints after launch | Presents/s | Quiet mean gap | Main 4w CPU | Game worker 124w CPU | Changing game worker CPU |
| --- | ---: | ---: | ---: | ---: | ---: |
| 130–200 s | 45.11 | 21.74 ms | 81.8% | 29.9% | 176w 88.5% |
| 210–280 s | 27.13 | 36.53 ms | 64.8% | 40.1% | 176w 90.1% |
| 320–360 s | 21.61 | 45.86 ms | 55.8% | 51.8% | 212w 88.9% |

This supports the report that moving gameplay can exceed 30 presents/s, while
the later stutter is still real. The 130–200 s window follows the approximate
kickoff time, but the log has no frame-specific marker for a quick pass, replay,
or camera pan. Presents are not a count of unique simulation frames.
Even in the fast 130–200 s phase, 175 of 2,942 unsampled present gaps (5.9%)
exceed 33.334 ms; in the slow 320–360 s phase, 681 of 869 (78.4%) do. Thus a
high *average* present rate does not mean a stable 30 FPS camera.

The changing worker remains close to a full core in all three windows. The
second worker (124w) becomes more active as cadence worsens, while the main
thread spends more samples inside guest or host waits. Its sampled guest PC at
`0x0093df30` is the copy routine already optimized in PERF25; the matrix block
`0x0112fb90` remains a hot sample across phases. No one block dominates enough
of the sampled wall time to justify promising a stock-clock 30 FPS lock from
another single block patch. This pattern motivates a broader x86 translation
or worker-synchronization improvement, with graphics timings still needing
their own measurement.

At 320–360 s host Present call duration rises to about 3.8–4.6 ms from roughly
0.3 ms in the earlier match windows. This is a secondary stall, not an
explanation of the whole 46 ms frame gap. The log cannot distinguish a camera
event from a shader/pipeline or swapchain effect at that exact time.

DXVK reports loading `dxvk.conf`, but the PERF43 archive does not contain that
file. It is inherited from the existing SD installation and its current contents
are unknown. Keep that same file for the control run; the log does not establish
that DXVK is using its default options.

## Same-NRO control before the next performance patch

`pes13-perf43-quiet-overlay.zip` changes only the two `profile` settings from
`1` to `0`, retaining the identical PERF43 NRO, game flags, DXVK, cache and
save. Install it over PERF43 after closing with HOME -> X. Compare the same
teams, stadium, camera and PES13 settings once at the current clocks and once
at stock clocks; note kickoff and the first fast pass/replay uptime. Save the
log before another launch rotates it. The `[BUILD]` marker stays PERF43 and
`[INIT] profiler off` confirms the quiet control. Reinstall the full PERF43
package if JIT sampling is needed again.

If the 130–200 s speed disappears when profiling is off in a matched scene,
the sampler's scheduling effect needs its own low-overhead experiment. If it
persists, the low windows identify the worker/graphics path to optimize without
adding a periodic sampler to a production build. No stock-clock FPS or 30 FPS
lock is claimed from this log.
