# PERF30 result: sustained worker limit, incomplete coverage of post-event stall

New private evidence is archived under `local/perf31/results`; hashes are in
`input-manifest.json`. `tools/audit-perf30-result.py` combines stage timings,
CPU reports and samples in `joined-analysis.json`.

| Input | Identity | Last interval endpoint |
| --- | --- | --- |
| current | PERF30, sampler off, diagnostics on | 290 seconds |
| previous-1 | PERF30, same startup null read | 30 seconds |
| previous-2 | New PERF29 control-sampling run | 230 seconds |
| previous-3, previous-4 | Previously archived PERF29 control runs | historical |

Current hash: `6e08d461a81106c69c89cd011514a12d9651607fe3f5ebb1a229981c170761fb`.
Sampled PERF29 hash: `1e4acf2e92b8a11d3293419499b2062f0718fbf32cc40de0a044ca574ff4f865`.

The user reports audio stayed smooth, gameplay remained in the teens initially,
and severe persistent slowdown began around 4:30 after launch. They also recall
an earlier build sustaining roughly 30 **in-game minutes**, not 30 FPS. The
exact older build is not confirmed. PERF25's archived report explicitly records
recovery after replay, making it a useful stability comparison; it is not proof
of a historical 30 FPS match baseline.

## CPU and observed cadence

PERF30 windows ending 130–230 seconds remain roughly 12.38–14.09 presents/s.
Worker 176 uses 94.2–96.3% of one core, worker 124 roughly 76–82.4%, and the
main thread roughly 48–52%. The already demonstrated game-worker bottleneck
remains. Audio progresses, while descriptor allocation counts stay at 4096 and
reported SLM allocation stays zero; this run does not support an SLM-growth
explanation. Smooth audio does not establish that the mixer costs no CPU.

| PERF30 endpoint | Presents/s | Whole host submit total | NVK driver total |
| --- | ---: | ---: | ---: |
| 250 s | 18.87 | 802.9 ms | 85.0 ms |
| 260 s | 17.37 | 1157.8 ms | 80.2 ms |
| 270 s | 17.66 | 1054.8 ms | 244.1 ms |
| 280 s | 17.78 | 299.6 ms | 46.1 ms |
| 290 s | 14.36 | 1178.8 ms | 82.0 ms |

These are totals over roughly ten seconds, not durations of one frame. The log
does not show a 2–3 presents/s collapse after the user-reported 270-second
point. Slow simulation or different image contents cannot be established from
present counts. It stops after replacement worker 216 starts, without a later
interval. Do not deny the user's slowdown or extrapolate its duration.

The newly available PERF29 sampled run does capture 6.59 then 2.60 presents/s
at 220/230 seconds. Host submit totals rise to 4.874/6.563 seconds. At 230 s,
worker 192 is 70.4% busy and its samples are 96% translated game code; worker
124 is 82.4% busy, predominantly translated game code. Main thread 4 is 9.4%
busy, with 79% of its samples in a native address wait. Symbolizing the exact
PERF29 ELF resolves `+0xbd930` to `horizon_futex_wait` and `+0xd8600` to
`NtWaitForAlertByThreadId`. That identifies waiting, not its owner or cause.
The sampler follows the busiest prior threads and does not reliably sample
the graphics submit thread once it becomes mostly blocked.

## Correction to PERF30 diagnostic coverage

The final PERF30 ELF's `nouveau_horizon_channel_submit` has **no** measurement
calls. The instrumented object in libvulkan was shadowed by the earlier shared
Horizon implementation in libEGL. The previous verifier checked the archive
object and global symbols but failed to check this selected function. The lack
of `channel_lock`, `reserve`, `throttle` and `kickoff` counters is therefore a
coverage defect, not evidence that these paths are free or unused.

The outer `channel_submit` and NVK stages do report. They are generally short,
while host submit is considerably longer. PERF30 also omitted signal unwrapping,
timeline point collection and full submit entry/cleanup. Nested timings cannot
be subtracted as exact exclusive time, but the gap warrants measuring these
paths before blaming shader execution or changing GPU clocks.

## Next targeted work

PERF31 replaces matching objects in **every** archive copy and checks calls
inside the final ELF. It measures submit entry/create/destroy, timeline signal
unwrapping/install/collection, fence query/wait and channel error scans.

Source audit found every native fence timeout, including zero-time queries
used by timeline garbage collection, scans channel error notifications.
PERF31 tests deferring repeated optional error scans for at most a 50 ms
query cadence on the same caller/device/syncpoint. It never skips the native
completion query or turns a timeout into success. Known device loss, actual
native errors, failed error scans and positive/infinite waits are preserved.

This is an evidence-guided experiment with a same-NRO control, not a demonstrated
root-cause fix. It may save little if the relevant polls are rare. Both the
persistent stall and the busy game worker still require hardware evidence.
CPU math, memory ordering, CALLRET policy, audio buffering and wait routing are
unchanged in the main experiment so comparisons remain interpretable.
