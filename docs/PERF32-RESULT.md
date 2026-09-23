# PERF32 result: sustained low cadence and an uncaptured corner slowdown

The new 143,956-byte input is archived at
`local/perf32/corner-result/pes13-nx.log`, SHA-256
`7b162320deca689bb8dbe7534c9c4059d202e2914162e144f9dffb577b761b1c`.
`python tools/analyze-perf32-result.py` regenerates the analysis and verifies
the existing full diagnostic package.

Unlike the prior quiet-labelled upload, this run **does identify PERF32**.
Scoped BIGBLOCK=3 is active; the CPU sampler is off. The user reports a small
subjective movement-speed improvement, continued camera stutter and slow
motion after a corner around five real minutes after launch. Whether that
slowdown recovers was not separately confirmed in the timing reply.

## Measured cadence

| Report endpoints since launch | Presents/s | Mean quiet gap | Gaps over 100 ms | Host present mean |
| --- | ---: | ---: | ---: | ---: |
| 130–170 s | 12.41 | 80.49 ms | 17 / 621 | 0.279 ms |
| 180 s | 7.59 | 131.96 ms | 32 / 76 | 0.674 ms |
| 190–270 s | 12.10 | 82.63 ms | 49 / 1090 | 0.272 ms |
| 280–290 s | 10.14 | 98.69 ms | 50 / 203 | 0.293 ms |
| 300 s | 16.89 | 59.11 ms | 1 / 169 | 0.272 ms |

The long low-rate sections alone can make camera motion visibly discontinuous,
even without isolated long stalls. This is not a demonstrated 30 FPS match.
At 12.10 presents/s, reaching 30 requires about a 60% shorter frame interval;
the later 16.89 presents/s window would require about 44%. These are frame
budget comparisons, not predicted optimization gains.

Host present is a narrow CPU-side call. Its short duration does **not** rule
out driver work elsewhere, queued GPU work or game-side rendering preparation.
Presents also do not count unique images or establish simulation speed.

## CPU, lifecycle and memory evidence

Worker 176 uses 86.7–87.4% of one core in the early group. Replacement worker
188 uses 87.0–88.1% through 190–270 s. Worker 124 remains near 78–81%, while
the main thread is around 46–50% through most of those periods. This remains
consistent with a busy game-worker limit, but the run has no sampled PCs to
identify exactly which instructions or waits consume this work.

Worker 176 exits before the 180-second report; worker 188 exits before the
280-second report. Worker 200 is present by 290 s. Thread balancing moves
some threads around these transitions. These are correlations, not proof
that the balancing policy caused the slowdown or that a specific transition
was the user's corner. No corner or scene marker is written into the log.

The completed PERF32 policy reports 78,947 compiled blocks, 4,367,484 guest
bytes and 15,602,112 native bytes by 300 s. These establish compilation and
selection, not executed instruction counts or CPU time saved. No new fault
or exit is recorded. The last available PROGRESS memory snapshot has 499 MB
free, code usage 61/64 MB and `audio_under=35`. PROGRESS uses a different
elapsed-time origin; its `180s` label must not be aligned directly to the
PERF8 timeline. The underrun counter is cumulative empty-queue observations,
not a timed recording of audible gaps. There is no demonstrated memory
exhaustion in this snapshot.

## What is missing

The last report is at 300 seconds, approximately the user-reported corner
time, and there are **no later reports**. The final measured cadence actually
rises. That does not contradict the reported later slowdown; it means its
post-corner state was not captured. The logger source has no five-minute
cutoff. Routine output is flushed every five seconds, so ordinary buffering
alone cannot explain a missing minute of subsequent reports.

Previous PERF25 runs used different scenes/timings and cannot establish a
matched speedup or regression from BIGBLOCK=3. In particular, the currently
available data do not identify a new driver bug or justify another arithmetic
or synchronization-policy change.

## Next required hardware evidence

Use the existing **full** `dist/pes13-perf32-diagnostics.zip`, closing the app
first and replacing its entire `switch` folder payload. Verification confirms
its NRO is byte-identical to the tested PERF32 main NRO; only `profile.txt`
and the `profile` field of `pes2013.wine-nx.txt` differ. It contains one NRO
and leaves block policy, audio, renderer, saves and game files unchanged.

The new log should show CPU sampler `2s/10s at 20ms`, followed by `[SAMPLE24]`
and `[PROF]` reports. Play through the corner, then continue for at least
60 real seconds **after** slow motion begins before closing. Save the log
before relaunching. Note elapsed real time since launch and whether normal
play recovers. The needed comparison is sampled work before and after the
same event, not another menu FPS result. Sampling has overhead; quiet and
sampled interval histograms remain separate.

No new performance fix is claimed from this report. Further changes should
follow the captured post-corner state. The >30 FPS kick-off target remains
unmet.

## Follow-up sampled run

The later PERF32 diagnostics log is archived at
`local/perf32/throwin-result/pes13-nx.log` with SHA-256
`8072ffe7ceccb76e23d345477fa1d62a6231732f47029ea2a10620a2735ebeab`.
It runs to about 571 seconds without a new fault or a newly persistent
post-event collapse. Its cadence is near 55–60 presents/s during the early
non-match portion, then about 12–18 presents/s during the active match. The
host present call remains roughly 0.2–0.5 ms while the busy workers are mostly
translated PES x86 code. This is consistent with a CPU translation limit, but
does not identify a single renderer function or prove the GPU is idle.

The user's throw-in observation is useful scene evidence: the brief ball-held
phase feels smooth, while active play resumes below 20 FPS after the throw.
The log has no scene timestamp, so it cannot label that interval as throw-in
or separate simulation, draw preparation and camera work. PERF33 is the next
scoped CPU experiment based on this clue.
