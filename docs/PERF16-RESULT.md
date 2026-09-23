# PERF16 result: translated game execution is the leading CPU bottleneck

The user reports similarly slow 3D with WineD3D and DXVK. Both supplied
logs identify the stable PERF15 runtime and the Compatible preset. The
DXVK run has sampling enabled; the WineD3D run has sampling disabled.
Their frame rates are therefore not a controlled renderer benchmark.

## Evidence

WineD3D really was selected: startup reports `Direct3D 9 Wine`, WineD3D
initializes its multithreaded command stream with `0x1`, and the progress
record contains OpenGL calls and presents. There is no DXVK version banner
in that log. The intervals ending at 120–170 seconds consume **3.09–3.17
CPU cores**. In the last interval, the main thread uses 82.2% of a core and
the two busy game-created workers use 89.0% and 94.9%.

The DXVK sampler provides stronger localization:

| Interval ending | Thread | CPU occupancy, % of one core | Samples in translated x86 | Samples attributed to EXE |
| --- | --- | ---: | ---: | ---: |
| 100–120 s | Main, 4w | 97.8–97.9% | 97.1–97.5% | 80.2–82.1% |
| 200 s | Main, 4w | 81.4% | 81.8% | 71.6% |
| 200 s | Worker, 124w | 76.9% | 78.2% | 77.2% |
| 200 s | Worker, 176w | 90.3% | 89.9% | 79.7% |

At 200 seconds, aggregate CPU occupancy is 3.06 cores and Vulkan presents
are 4.99/s. The three busy game threads have only 0.3–0.8% of samples in
native runtime code. D3D9.DLL accounts for 1.1% of main-thread samples.
This supports a CPU limit dominated by translated game execution in the
sampled intervals. It does not establish the fraction due to useful game
work versus translation inefficiency, memory operations or spin loops.

Two measured areas deserve investigation:

- Main thread and worker 176 repeatedly concentrate in EXE RVAs around
  `0xd2fba0–0xd2fda0`. The individual address buckets are 32 bytes wide;
  these are hotspots, not identified function boundaries.
- Worker 124 concentrates around `0x537a00`, `0x53b860` and `0x53cfc0`.

The on-disk EXE's `.text` section has approximately 8 bits/byte entropy,
and static decoding at these locations does not yield credible function
bodies. Treat it as packed/encoded until runtime bytes are captured;
do not name these routines or patch instructions using that static decode.
No game file or runtime configuration was changed during this analysis.

## Waits and limitations

Native wait samples were symbolized against the exact PERF15 ELF at
`/home/blekjek/pes13-build/runtime-perf15-guest-exceptions/wine-nx-runtime.elf`:

| Runtime offset | Symbol |
| --- | --- |
| `0xbd0f0` | `horizon_futex_wait` |
| `0xd6094` | `NtDelayExecution` |
| `0x16c5f0c` | `condvarWaitTimeout` |
| `0xd7de4` | `NtWaitForAlertByThreadId` |
| `0x9ca30` | `horizon_pipe_read_r` |
| `0x9cec0` | `horizon_pipe_write_r` |

These sampled waits are wall time; they cannot be added as CPU execution
cost. At the end, main thread 4 reports a critical-section timeout waiting
for thread `0040` (decimal 64). Investigate if it recurs without sampling;
this one line does not establish the cause of sustained low 3D frame rate.

The sampler pauses four previously busy threads every 2 ms, changing
timing. It includes blocked time and does not sample every render/driver
thread. Worker 176 appears in only one complete sampled interval. Scene
assignment follows the user's sequence, without synchronized scene markers.
Dropped address buckets undercount module attribution; total x86-category
counts still include these samples. GPU timings are not available here,
so GPU/driver contribution is not excluded.

WineD3D's zero `[PERF8] fps` is expected because that counter is Vulkan-only.
Its single OpenGL progress aggregate does not isolate a match interval;
no numeric WineD3D match FPS can be derived reliably from this log.

## Next step

Restore the existing PERF16 DXVK control overlay for normal play, with
profiling off. Preserve the stable PERF15 NRO, Compatible preset and saves.
The next targeted experiment should capture a small, bounded snapshot of
the hot guest code and its generated ARM64 blocks during 3D, outside the
paused-thread sampling section. Use that to distinguish repeated game
computation, inefficient translation and polling before changing flags.
Any subsequent A/B test should change one identified cost and compare the
same scene and clocks with sampling disabled. These logs do not yet
demonstrate that 30 FPS is achievable.

## Reproducibility

`tools/analyze-perf16-result.py` archives the supplied inputs without
overwriting a different archived run, and writes per-interval measurements
to `local/perf16/results/analysis.json`.

| Input | Bytes | SHA256 |
| --- | ---: | --- |
| `pes13-nx-test-1.log` | 177870 | `f9d1f07652683f9528c78c2e82ade9ee6bf46a46609cff8ba61508f8fe917cc2` |
| `pes13-nx-test-wined3d.log` | 39130 | `1f7798c3c13e21f593500d7dff0ee6bf0dfa64b8030c45414d029207658560c2` |
