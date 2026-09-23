# PERF15 hardware result: startup stable, match about 4 FPS

The user reports stable startup and a successful match. The supplied log
identifies PERF15, Box64 Compatible with BIGBLOCK=0, DXVK 3.1.1, NVK 26.2.2
on GM20B, a 1280×720 swapchain, and profiling/verbose logging off. It contains
no `[EXC]`, `[BOX64] status=` or `[EXIT]` lines. This is one successful run;
the user's stability report is broader than the single log can establish.

Archived input: `local/perf16/perf15-stable-3d-slow.log`, 61,776 bytes,
SHA256 `f3c219a2e50857c72d06eef5462a9b2039ee610d94aab1f14d05c07d7f12739c`.
`tools/analyze-perf15-result.py` preserves the input and produces the numeric
summary in `local/perf16/analysis.json`.

| Interval endings | Successful presents/s | Total CPU |
| --- | ---: | ---: |
| 40–60 seconds, consistent with 2D/menu | 46.85–57.74; weighted 51.19 | 0.75–2.30 cores |
| 140–190 seconds, consistent with the match | 3.98–4.20; weighted 4.08 | 2.77–2.84 cores |

Screenshots are not timestamp-aligned with the log, so scene assignment is
inferred from the user's sequence. The late interval has 245 presents in
60.081 seconds, corresponding to about 245 ms per presented frame. Reaching
30 FPS requires about a 7.4× throughput improvement from this run.

Late thread occupancy: game-created thread 176 uses 91.3–96.7% of a core,
game-created thread 124 uses 80.7–90.3%, and main thread 4 uses 62.8–66.0%.
Both workers start at the EXE's common routine 0x4da0e3. That address does
not identify their work. Useful execution, emulation, spinning and driver
calls must be distinguished with samples taken during 3D itself.

The host Vulkan present call averages 0.209–0.355 ms in those intervals.
This is **not GPU execution time** and does not exclude waits or driver
overhead elsewhere. Server `select` durations include overlapping waits;
they cannot be added to infer CPU load. Thread 72 is around 1% and suspend
requests are roughly 2,400–3,100 per ten seconds, so the previously identified
suspend retry storm is no longer the most obvious dominant activity.

The log is about 60 KiB for the entire run, with verbose and sampling off.
There is no evidence here of the earlier huge per-operation trace flood.
There are still HMAP failures during startup, but no captured allocation
exception and the match is reached; they are not proof of the frame-rate
bottleneck. The code arena grows once late in the run, which also does not
establish shader compilation or translation as the dominant sustained cost.

The message about an extended constant set for software vertex processing
is emitted when DXVK's `CanSWVP()` is true. It alone does not prove active
CPU software rendering or a software-vertex bottleneck. See the
[DXVK 3.1.1 device implementation](https://github.com/doitsujin/dxvk/blob/v3.1.1/src/d3d9/d3d9_device.cpp).

The user confirms their faster L4T/Winlator comparison was also 1280×720.
That makes the comparison relevant, but exact driver, Box64 settings,
renderer version, scene and clocks still differ or remain unrecorded.
Vulkan/DXVK is not an automatic performance ordering: this installation uses
the Horizon NVK port; WineD3D defaults to OpenGL, using nvc0 in this build.
Both still involve the x86 CPU translation and Wine synchronization paths.

Next: preserve the successful PERF15 NRO/ABI4 pair, sample its busiest
threads during team selection and a match, and optionally compare the
existing WineD3D path with profiling off. See [PERF16.md](PERF16.md).
