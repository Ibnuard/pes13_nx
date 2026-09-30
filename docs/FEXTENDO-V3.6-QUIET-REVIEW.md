# v3.6 review: trace OFF, remaining first-match stutter

The user reports that disabling profiling/trace restored smooth camera motion,
but the first kickoff and early actions still stutter. Kickoff is approximately
two minutes **since Play**, not an exact event marker. This capture does not
establish a second-match kickoff time. The remaining freeze is **not fixed or
fully attributed** by this review.

## Evidence and reproduction

Preserved capture: `local/fex3/review-trace-off-a54ddd06d1/device.log`, 391,931 bytes.
SHA256: `a54ddd06d1a10ad76d79cce24237468c2706cb3f28842c8eb51ae7cde6e34b36`.
Play origin: `11084859988545`, 19,200,000 ticks/second, line 12.

```sh
python3 -B tools/analyze-fextendo-quiet.py \
  local/fex3/review-trace-off-a54ddd06d1/device.log \
  --play-range 110 140 \
  --output local/fex3/review-trace-off-a54ddd06d1/quiet-analysis.json
python3 -B tests/fextendo_quiet_analysis.py
```

Configuration confirmed in the capture:

- Short trace OFF (line 3); execution sampler OFF (lines 56–57).
- Fast API and polling ON (lines 36–37).
- DXVK 3.1.1, VSync ON (lines 14–15); JIT128 (line 242).
- FEX disk cache OFF (line 77).
- Stable balancing; effective DXVK core-3 offload OFF (lines 35–39).
- The memory-budget extension filter remains active (line 29).
- Timestamp overlay OFF; the Play origin is still recorded (line 12).

The user's camera result supports keeping detailed diagnostics OFF during
normal play. It does not isolate the cost of each diagnostic component or
establish an FPS improvement from controlled identical scenes. Aggregate JIT,
frame, file-read and background log counters still run in this mode.

## What is recorded near the approximate kickoff

These are completion gaps, timestamped from the actual Play counter:

| End since Play | Present completion gap | Present-thread CPU | Submit wall time | Log line |
| --- | ---: | ---: | ---: | ---: |
| 01:52.392 | 56.556 ms | 0.747 ms | 37.515 ms | 2120 |
| 01:55.708 | 52.472 ms | 0.650 ms | 27.447 ms | 2121 |
| 02:02.430 | 64.833 ms | 0.871 ms | 49.125 ms | 2180 |

The observer reports no drops in these two batches. Across the entire capture
it drops 71 records, and some batches have no drop report. A whole-session
maximum must not be relabelled as kickoff: the 753.509 ms record at T+65.236 s
(line 1668) occurs substantially earlier than the user's estimate.

The two containing PROGRESS batches are labelled 125 s and 135 s, with different
clock origins from Play. Their respective read-counter deltas are:

| PROGRESS batch | Completed SD reads | Read wall time | Graphics pipelines | Driver-cache gets |
| --- | ---: | ---: | ---: | ---: |
| 125 s, line 2087 | 1 | 3 ms | 0 | 0 |
| 135 s, line 2149 | 8 | 45 ms | 0 | 0 |

These batches do not show a large asset-read burst or new graphics pipeline
creation. They do **not** rule out every SD write/flush, shader work outside the
measured entry points, or in-flight work. Their counters are asynchronous and
cannot assign those 45 ms to the precise kickoff instant.

The 64.833 ms frame gap is real. It is not evidence of a several-hundred-ms
render freeze at precisely T+120 s. A simulation/input stall can coexist with
continued presentation; these logs do not measure ball/camera progression.
Likewise, submit wall time includes waiting and descheduling. It is not a GPU
execution timer, and Present-thread CPU is not game-thread CPU.

## First-use translation is still substantial

Quiet mode omits the absolute JIT-origin record. Therefore the following rows
use **compiler uptime**, not an asserted Play timeline. Values are differences
between complete cumulative reports; they are not prorated to guessed events.

| Compiler uptime | Span | CompileCode calls | Completed-call wall time | New calls >20 ms |
| --- | ---: | ---: | ---: | ---: |
| 100.189–150.206 s | 50.017 s | 6,900 | 7,863.238 ms | 0 |
| 250.246–300.268 s | 50.022 s | 537 | 705.702 ms | 0 |

Source lines: 1923→2263 and 2976→3328. The early span has approximately 11.1
times the accumulated compiler wall time of the late span. This is **not** an
11-fold CPU/FPS improvement: calls span threads, include scheduling and races,
and may start before the selected interval. CompileCode is nested inside
dispatch_compile; adding them would double-count work.

At compiler uptime 330.285 s the capture records 53,274 CompileCode calls and
40,877.967 ms total wall time (line 3582). Many short calls can consume the
frame budget even without an individually long compiler call. This is
consistent with first-use work declining and the user's earlier report that
subsequent matches in the same process run better. It does not prove that
compilation alone causes every early stall.

## Engineering decision

Preserve the current smooth-camera control: trace/sampler OFF, fast API ON,
the existing renderer, clock and balancing configuration. There is no evidence
here to justify moving DXVK back to core 3 or changing DXVK versions again.
Do not require another identical run merely to reconfirm the same symptom.

Following the user's clarification, reducing first-use compiler/runtime CPU
cost is the primary next step. The [decoder-worklist candidate](FEXTENDO-DECODE-WORKLISTS.md)
removes small node allocations without depending on persistent cache reuse.
Cache persistence remains complementary; any next cache implementation must
demonstrate reuse rather than repeat the old unverified `fex_diskcache=1` trial:

1. Report the effective FEX cache state and open failure at initialization,
   including the resolved bucket and index size. The current launcher message
   reports only the requested flag.
2. Count successful code loads, misses, successful stores and failed stores
   separately. Drain small aggregate counters through the existing background
   logging path; avoid compiler-table scans or thread suspension.
3. Verify reuse after closing/reopening the application before claiming cache
   persistence works. Compare CompileCode work as well as frame gaps. A shader
   cache hit does not establish a FEX translated-code hit.
4. Only then consider loading cached work during the loading screen. If an
   actual first-ever launch is to avoid compilation, it needs a compatible
   prebuilt cache or a validated warmup profile; a progress dialog by itself
   cannot compile execution paths that have not been identified.

Source inspection confirms the pinned upstream FEX already has a disk-cache
lookup/load path before CompileCode and an asynchronous writer. It partitions
the default path using format, guest mode, configuration and host-feature
hashes. The project trial used mapping OFF, anonymous-code caching OFF and
memory LRU OFF; those settings do not prove that opening, writing or reusing
the database succeeded. No specific cache failure has been proven from this
capture. Do not replace these mechanisms with serialized raw JIT pointers or
disable executable-code invalidation to force apparent hits.

This review adds a quiet-log analyzer with six regression tests. It changes no
runtime, game settings or binary, and makes no new device-performance claim.
