# PERF36 result — no demonstrated match-throughput breakthrough

The supplied run is archived at `local/perf36/results/1a3daf3f4bd5/pes13-nx.log`
(141,938 bytes). `analysis.json` records its full SHA-256 and parsed intervals;
`captures/` contains decoded bounded snapshots. The log identifies PERF36,
with sampling off and scoped PERF33 policy active. No unhandled fault or exit
is recorded in this run.

| Report endpoints | Weighted present rate | Interpretation limit |
| --- | ---: | --- |
| 41–61 s | roughly 50–59 per interval | Early scene, not measured moving gameplay |
| 101–111 s | roughly 18 per interval | No synchronized scene marker |
| 131–291 s | 12.356/s over 170.207 s | Later gameplay candidate, includes transitions |

For 131–291 s, 2,103 quiet gaps average 80.948 ms. Of these, 1,748 are
66.7–100 ms; 93 exceed 100 ms, including seven over 200 ms, none over 500 ms.
Host-present averages 0.280 ms, measuring that call only. The late busy worker
is around 91% of one core and worker 124 around 78%, with total occupancy about
2.7 cores. This is compatible with a busy CPU path but does not isolate game
simulation, translation, polling or the full graphics driver. Server select
times overlap across threads and include blocked wall time, not CPU time.

There is no synchronized PERF35 control scene, so the difference between this
run and its prior log is not a measured causal regression. However, PERF36 has
clearly not established the desired 30 FPS match. Reaching 33.3 ms from this
80.9 ms cadence would require about a 59% reduction in the critical interval.

The earlier scalar SSE micro-test remains valid as an instruction-count result,
not a game speedup. The game's captured blocks contain much x87 arithmetic.
These captures are selected at translation time, not weighted by execution:
they do not prove which x87 operation dominates. The latest run has no PC
samples. Archived PERF32 samples point toward translated game workers, but
they predate changes and have no timestamped throw-in interval.

## Next evidence: PERF37

PERF37 retains the PERF36 execution policy and adds bounded sampling detail:
the actual ARM opcode word, its guest block address and both block sizes. It
does not add counters to executed guest instructions. Full retained opcode
counts and the twelve most sampled blocks per thread are reported. The existing
module/native/SVC profiler remains, allowing inspection of non-JIT work too.

The stationary throw-in observation is a useful workload contrast. It does not
prove one fix will make active simulation equally cheap: animation, simulation,
visible objects and synchronization can differ. A recorded comparison is
needed before replacing a routine with native code or changing its math policy.
No gameplay logic, AI, physics rate, sleep or frame duplication is changed.
