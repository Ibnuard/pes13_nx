# PERF26 result and Linux/Android comparison limits

The new current log is 153,939 bytes, SHA256
`e5be3bbb56e382fe2b0fa669bdce2e14e07a08cfc18c8a2a2e9345f873d5f33d`.
It is archived in `local/perf27/results`. All four previous logs are duplicates
of the prior upload; they are not four further PERF26 trials.
Reproduce the report with `python tools/analyze-perf26-result.py`.

PERF26 is active: the post-present environment reports CALLRET=2, SAFEFLAGS=2,
FASTROUND=1, X87DOUBLE=1, STRONGMEM=1 and BIGBLOCK=0. The captured native block
at guest 0x9379f0 contains the expected matched native return and mismatched
jump-table fallback. This confirms emission, not the runtime hit rate of that
fast path. CPU sampling and verbose logging are off. No new fault/exit is logged.

| Report windows ending | Presents/s | Mean quiet gap | Mean host present |
| --- | ---: | ---: | ---: |
| 40–50 s, menu candidate | 53.11 | 19.60 ms | 0.66 ms |
| 130–290 s, match candidate | 16.30 | 61.33 ms | 1.15 ms |
| 250–290 s, before worker transition | 16.28 | 61.41 ms | 1.03 ms |
| 300–330 s, after worker transition | 14.57 | 68.64 ms | 7.76 ms |

Frame-gap windows can contain a boundary gap from the preceding interval, so
their average need not be precisely the reciprocal of interval present rate.
Presents are not unique-frame or simulation-update counters. Scene labels are
inferred; no goal/foul/replay timestamp is recorded. This run does not establish
a meaningful CALLRET speedup relative to the unmatched earlier scenes.

In the long 3D period, worker 176 occupies 91.6–94.0% of a core, worker 124
80.1–80.5%, and main thread 4 59.8–63.1%. Prior PERF25 sampling was mostly
translated game code on the heavy workers; the current quiet run has no PC
samples and cannot attribute all that CPU time to useful work versus polling.

Between the reports at 290 and 300 seconds, worker 176 exits and worker 184
starts. Total occupancy drops from about 2.94–2.97 cores to 2.33–2.45 later.
Meanwhile host present duration rises sharply and remains elevated through
the end. Gaps over 100 ms rise from 4/815 (0.49%) before the transition to
101/583 (17.32%) afterward. This supports the reported worsening stutter.
It does not establish that the worker replacement causes it, or that a
specific foul is the trigger.

Host-present wall time includes driver waits and possible descheduling. It
does not directly measure GPU execution. The additional roughly 6.7 ms inside
present is close to the 7.2 ms rise in mean gap, but asynchronous overlap and
scene changes prevent treating their subtraction as a causal decomposition.
The startup log selects FIFO presentation; there is no logged late swapchain
reset. Timing instrumentation around acquire, submission, fence waits and
presentation is needed to distinguish pacing from GPU or scheduler waits.

## Why the CPU path is not automatically equivalent to L4T

The same Switch CPU and related Box64 dynarec do not imply the same software
execution path. Box64 distinguishes its Linux application build from its Wine
WoW64 backend. Wine configurations for a 32-bit game can also differ (Box86,
Box32, or WoW64 through Box64). The user's exact Linux/Android versions and
mode are not recorded, so no specific one is assumed here.

Autorun's Horizon port reimplements Wine's server, memory, exceptions and
drivers within one process. Our port inherits that design. Scheduling,
synchronization, code protection/invalidation, native-library boundaries and
driver calls therefore differ from a Linux-hosted Wine stack. These are
possible sources of different overhead; architecture differences alone do
not prove which one accounts for the remaining performance gap.

The current CPU dynarec is active and emits cached ARM64 code; it is not
running the entire game in the interpreter. Executing translated instructions
still carries costs for x86 semantics, floating point, memory ordering and
dispatch. Compiling the translator with a higher C optimization level is not
equivalent to making its generated guest code proportionally faster.

The reported >30 FPS L4T result at 1280x720 is useful evidence of hardware
capacity for that configuration. It is not proof of an identical CPU path,
driver, preset or guaranteed Horizon frame rate. A matched Linux trace of the
same scene and hot routines is needed before assigning the difference to a
particular layer. At the current 61 ms frame cadence, 30 Hz requires reaching
33.3 ms, roughly a 46% reduction in total frame time.

This turn preserves the build and packages. It archives/analyzes evidence;
it does not produce another unvalidated preset change or a PERF27 NRO.

Primary references checked 2026-09-22:

- [Autorun technical design](https://github.com/danfromtico/autorun/blob/main/documentation/technical.md)
- [Box64 execution and native-library integration](https://github.com/ptitSeb/box64/blob/main/README.md)
- [Box64 build modes and dynarec options](https://github.com/ptitSeb/box64/blob/main/docs/USAGE.md)

Upstream documentation evolves; local runtime source and captured instructions
remain the evidence for this specific artifact. In particular, generic WowBox64
option limitations do not replace inspection of Autorun's custom return-site
trap handler.
