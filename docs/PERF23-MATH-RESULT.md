# PERF23 math-control hardware result

The user reports smoother 3D with the math-control overlay, remaining stutters,
and intermittent loading failures. This successful run confirms scoped
FASTROUND=1, X87DOUBLE=1, SAFEFLAGS=2, secondary balancing enabled, and sampling
off. It contains no failed-launch history. The earlier PERF23 main-run input
was replaced at the supplied path before it was archived; these results refer
only to the later math-control input.

Archived input: `local/perf24/perf23-math-control-result.log`, 101,519 bytes,
SHA256 `4c704602b75d1d751098d5cd7eae56436edfb8fcc15a918b2de8460d74fa5b47`.
Reproduce the numerical summary with `tools/analyze-perf23-math-result.py`.

The 40/50-second windows report 50.75 and 55.46 presents/s. Windows ending
120–150 seconds range from 15.68 to 19.96. A late window ending at 170 seconds
drops to 6.80, followed by 15.38, 14.18 and 12.38. Thread 176 exits before the
160-second report; thread 188 subsequently starts, grows to 91.7% of a core,
then exits before the 200-second report. Thread 124 remains near 80%.
Those worker IDs and their common entry address do not identify their jobs.

Secondary balancing moved audio thread 52 to a freed core. This alone did not
eliminate the reported stutter. There is no evidence for treating the new
balancer as a sufficient solution, or for another blind affinity change.

The 10-second reports cannot locate individual long frames or distinguish
useful game work, translated math, waiting, compilation and driver work.
Thread occupancy supports continuing CPU pressure, but does not identify a
function. Host-present time is not GPU execution time. Presents are not a
simulation-speed measurement. Scene assignment and the foul's exact position
are not recorded, so this is not a controlled FPS comparison.

The initial timer audit finds that interpreted and translated RDTSC both call
the same nanosecond ReadTSC helper (`box64_rdtsc=1`); QueryPerformanceCounter
uses Horizon interrupt time with a matching 10 MHz frequency. This does not
establish that every game timing path is correct, but supplies no reason to
change the clocks speculatively.

Next baseline: keep math-control and collect bounded CPU samples and present
gap histograms. Loading diagnosis needs the retained `previous-*.log` files,
because the supplied successful run cannot reveal the failed run's state.
