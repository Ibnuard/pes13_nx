# PERF25: smoother match cadence, remaining CPU and transition work

The user reports smoother play but still below roughly 20 FPS, with marked drops
during replay and visible stutter on fast or lofted balls. The user confirmed
that performance returns to its previous level after replay; this report does
not reproduce the older permanent post-event slowdown. Last confirmed clocks
are CPU 1728 / GPU 768 / RAM 1600 MHz, at 1280 x 720. No subsequent clock change
has been reported.

The current log is the only new PERF25 run: 131,906 bytes, archived under
`local/perf26/results/pes13-nx.log`. Its SHA-256 is recorded in
`local/perf26/perf25-analysis.json`. Previous-1 through previous-4 are byte-identical
to four files from the prior upload: respectively the successful PERF24 run,
two failed PERF24 boots and the older PERF23 math-control run. They must not
be treated as four failed or successful PERF25 attempts.

## What is confirmed

- Build is `pes13-nx-0.2.0-perf25-paircopy`, CPU sampler off, verbose off.
- SAFEFLAGS=2, X87DOUBLE=1, scoped FASTROUND=1, STRONGMEM=1, BIGBLOCK=0,
  CALLRET=0. The existing matrix and rounding fusion patches remain active.
- Pair-copy has four accepted translation-pass checks. More importantly, its
  actual captured ARM64 loop is byte-identical to the tested optimized emitter.
  This proves generation, not how often its alignment-dependent fast branch ran.
- The run reaches 300 seconds with no recorded unhandled fault or exit. This
  single successful run does not establish that the intermittent boot bug is fixed.

## Cadence

These groups use ten-second report endpoints. Scene names are inferred from
the user's sequence, not timestamped game events.

| Report endpoints | Presents/s | Mean gap | Gaps >100 ms | Gaps >200 ms |
| --- | ---: | ---: | ---: | ---: |
| 40-60 s | 53.15 | 18.81 ms | 10 / 1600 | 5 / 1600 |
| 130-200 s | 15.26 | 65.54 ms | 2 / 1222 | 0 / 1222 |
| 210-220 s | 13.73 | 72.65 ms | 28 / 275 | 2 / 275 |
| 230-300 s | 14.36 | 69.65 ms | 12 / 1150 | 0 / 1150 |

In the middle section, 1,152 of 1,222 gaps fall between 50 and 100 ms. Fast
motion can look discontinuous at this cadence even without occasional long
stalls. The broad improvement is consistent with the user's report, but an
isolated percentage gain over PERF24 cannot be assigned: sampling and scenes
differ. Reaching 30 presents/s requires roughly 33.3 ms, about half the current
steady frame interval. A frame limiter does not supply that missing throughput.

Worker 176 uses 91.1-92.0% of one core in the middle section, while 124 uses
56.5-59.2% and the main thread 57.2-60.6%. Around the reports ending 210-220 s,
176 exits, replacement threads appear and balancing moves them. The final busy
worker 188 is at 87.4-88.2%, with 124 at 58.3-60.3%. No persistent late starvation
like the old unbalanced layout is demonstrated. A worker's purpose cannot be
inferred from its generic thread-entry address.

Mean host-present call time increases from 0.333 ms in the middle section to
4.943 ms late. That is a real change worth investigating, but still much smaller
than the 69.65 ms present gap. These timings exclude other renderer/driver work
and are not GPU execution measurements. The 210-220 s transition cannot yet be
identified specifically as a replay or a foul. Aggregated server `select` wait
time spans multiple outstanding waits and must not be interpreted as CPU time.

## Startup evidence

PERF25 successfully captured the decoded startup block at `0x115c356`. Its
instruction at the previously failing PC `0x115c36f` reads `[esi]`. Preceding
branches can set EAX=0 and then ESI=EAX+4, matching the old read-of-address-4
faults. The unresolved question is why the preceding lookup/type check returned
that value. The code is not changed or forced to succeed. No new failed boot
was supplied in this upload.

## Next measurement, using the existing NRO

The dominant worker still has high CPU utilization, but this run has no sampled
PCs. Enable the already-built `pes13-perf25-diagnostics.zip` overlay to sample
the exact PERF25 runtime during the reported problem. This changes only
`profile.txt` and the `profile` field in `pes2013.wine-nx.txt` relative to the
main package. It does not change copy, math, renderer or NRO.

1. HOME -> X -> Close, then extract the diagnostics overlay at the SD root.
2. Use the same clocks, teams, stadium and camera. After reaching the match,
   play normally for about 30 real seconds, try the fast lofted ball and replay,
   then continue for 30 real seconds after returning to play. Note approximate
   real time since launch for each event. The current report already confirms
   that the replay slowdown recovers; flag it only if that behavior changes.
3. Return the current log and any available previous logs before further launches.
4. Reapply the main `pes13-perf25-paircopy.zip` afterward to turn CPU sampling off.

Sampling runs for two seconds in each ten-second cycle at 20 ms intervals and
can perturb timing. Its purpose is identifying functions and waits during the
problem; it is not an uninstrumented FPS benchmark. Do not clear caches or saves.
The existing small same-NRO control can separately disable only pair-copy for
a matching-scene comparison if needed.

Reproduce this analysis with `tools/decode-perf17.py` and
`tools/analyze-perf25-result.py`. No speculative arithmetic, return-cache or
memory-ordering setting was changed for this report.
