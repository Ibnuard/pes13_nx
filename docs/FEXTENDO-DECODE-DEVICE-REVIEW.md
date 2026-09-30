# Decoder worklists: device feedback and remaining first-use stutter

The user reports that the inline-64 decoder experiment shortened the stutters,
but they still occur at the first kickoff and during the next few minutes of
play. The target is this gameplay period, not loading screens or menus. No
exact kickoff timestamp was supplied for this capture. The remaining symptom
is not fixed or fully attributed by this review.

## Captures and effective settings

| Capture | File | Bytes | SHA256 |
| --- | --- | ---: | --- |
| Previous quiet baseline | `local/fex3/review-trace-off-a54ddd06d1/device.log` | 391,931 | `a54ddd06d1a10ad76d79cce24237468c2706cb3f28842c8eb51ae7cde6e34b36` |
| Latest experiment | `TEST RESULT/fex-runtime.log` | 435,447 | `77015b9ace4cc9332c9e555336dc4733700cf8bd0924d5f30b6195daada8457e` |

Line references below are one-based and refer to these exact bytes. The latest
log confirms `inline worklists=64` at line 240. Short trace and execution
sampling are OFF (3, 79), fast API and polling ON (58, 60), DXVK 3.1.1 with
VSync ON (36-37), JIT128 (99), FEX disk cache OFF (100), and stable balancing
with effective DXVK core-3 offload OFF (57, 61-62). These match the important
settings in the [previous quiet review](FEXTENDO-V3.6-QUIET-REVIEW.md).

This is a logging-enabled experimental run. It is not evidence from the later
production NRO that suppresses logging.

## What improved in the counters

Compare complete cumulative JIT reports near 330 seconds of **compiler
uptime**, not time since Play. The reports contain almost the same number of
CompileCode calls:

| Metric | Previous | Latest |
| --- | ---: | ---: |
| Compiler uptime | 330.285 s | 330.698 s |
| CompileCode calls | 53,274 | 53,243 |
| CompileCode accumulated wall time | 40,877.967 ms | 38,193.255 ms |
| Mean wall time per completed call | 767.32 us | 717.34 us |
| Longest completed CompileCode call | 62.365 ms | 48.164 ms |
| Calls over 50 ms | 3 | 0 |
| Calls over 20 ms | 23 | 43 |
| Nearby native allocation counter | 4,948,810 | 3,520,104 |
| Native live / peak storage, KiB | 21,813 / 26,124 | 21,817 / 26,142 |
| Native allocation failures | 0 | 0 |

JIT sources: previous line 3582, latest line 3702. Allocator sources: previous
3585, latest 3710; these are nearby independent samples, not atomic samples
at the exact compiler-report instant.

The latest capture records 6.57% less accumulated compile wall time, 6.51% less
mean time per call, and 28.87% fewer native allocation calls at these samples.
The lower allocation count supports the mechanism of the
[decoder worklist change](FEXTENDO-DECODE-WORKLISTS.md). It is not an allocation
profile attributing every saved call to that change. Storage use is essentially
unchanged: fewer allocation operations do not mean a 29% reduction in RAM.

The tail result is mixed: the maximum and over-50-ms count fell, while the
over-20-ms count increased. These are two uncontrolled gameplay captures with
different scheduling and paths through the game. They support continuing the
optimization, but do not establish an FPS gain, a measured reduction in kickoff
stutter duration, or uniformly improved frame pacing.

The early 100-150-second compiler interval illustrates the comparison limit:

| Compiler interval | Calls in interval | Completed-call wall time | Mean per call |
| --- | ---: | ---: | ---: |
| Previous 100.189-150.206 s | 6,900 | 7,863.238 ms | 1,139.60 us |
| Latest 100.572-150.593 s | 4,759 | 5,355.011 ms | 1,125.24 us |

Sources: previous 1923 to 2263; latest 1977 to 2360. Most of the total reduction
in this interval comes from fewer calls; mean cost falls only 1.26%. Do not
describe the roughly 32% total reduction as a per-call speedup. Timers include
waiting and descheduling, and calls may begin before the interval. CompileCode
is nested inside dispatch_compile; adding their totals double-counts work.

## Remaining frame gaps and first-use graphics work

Play origin is tick `11204119428490`, at 19,200,000 ticks/second (latest line 35).
The 471.612-ms Present completion gap at line 2524 ends at **T+161.656 seconds
since Play**. Its Present-thread CPU time is 0.813 ms; submit time is 10.288 ms.
This does not locate the whole stall on that thread or establish its cause.

The containing report is labelled `PROGRESS 175s` (2483), which uses a different
clock origin from Play. It contains:

| Work reported in the batch | Count | Accumulated wall time | Sources |
| --- | ---: | ---: | --- |
| Graphics pipeline creation | 147 | 1,817.427 ms | 2502 |
| Driver-cache gets | 258 | 1,750.456 ms | 2504 |
| Completed SD reads since preceding report | 722 | 1,144 ms | 2387 to 2483 |

Driver-cache gets are nested in pipeline work; these totals must not be added.
All 258 reported gets are cache hits (2505), which may include entries created
earlier in the same run. A hit still has CPU cost and does not demonstrate FEX
translated-code reuse. These asynchronous batches show a graphics/SD burst
near a real gap, not that these operations exactly explain its 471.612 ms.

Other gaps occur without a large graphics burst. For example, the 103.052-ms
gap ending at T+138.873 s (2276) has 0.734 ms Present-thread CPU and 85.746 ms
submit wall time. Its batch reports five graphics pipelines totaling 22.834 ms
(2257), rather than the later 147-pipeline burst. Submit and wait timings
include parking and scheduling; they are not GPU execution timers.

There is no exact kickoff marker or simulation-progress measurement. Do not
reuse the previous capture's approximate kickoff time as an event marker for
this run. The latest and previous captures also drop 69 and 71 gap records,
respectively. Frame completion observations cannot fully describe ball, input,
or camera stalls.

## Next bounded experiment

Update, 29 September 2026: the subsequent DFE predecessor experiment was
reverted at the user's request after a reported performance regression.
The active DLL has returned to the preceding inline-64 decoder build.
The proposal below is retained as historical context, not an active change.

Keep the working decoder change and reduce another concrete source of
first-use compiler allocation: predecessor scratch storage in the
`RedundantFlagCalculationElimination` pass. The proposed candidate stores the
first two predecessor entries inline and retains dynamically growing storage
for larger cases. It must preserve predecessor ordering, duplicates, the
existing data-flow algorithm, and overflow behavior; two is an inline capacity,
not a limit on supported control-flow graphs.

This is a compiler-storage experiment, not a measured fix for gameplay
stutter. Validate its behavior against the original container and pass before
shipping a candidate. Its Switch performance remains unmeasured until a new
device run. Keep JIT block limits, renderer, invalidation, timing, affinity,
and game settings stable so the next change has a clear scope. The remaining
pipeline and asset bursts warrant separate targeted work; this log does not
justify arbitrary JIT block-size increases, another DXVK switch, or restoring
core-3 offload.
