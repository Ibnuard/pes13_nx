# PERF35 CPU/pipeline experiments

**Superseded experiment, 2026-09-23:** These global-preset packages are not
the recommended next test. PERF36 fixes the ignored PERF33 FASTNAN override
inside the emitters while retaining the baseline global settings. Neither
short host-present times nor these configuration suggestions establish the
entire graphics-driver cost. The current-DXVK A/B result also had a warm/cold
cache difference, so it was a provisional choice rather than an isolated
renderer benchmark.

The DXVK A/B logs show that the retained current DXVK is the better renderer,
but normal gameplay still runs around 17–20 presents/s. The Vulkan present call
is roughly 1 ms while a frame takes roughly 55–60 ms, and a translated game
worker occupies about 85–91% of one core. This is therefore a CPU/Box64/game
path experiment, not a frame limiter.

Both packages reuse the PERF34 current NRO and current DXVK DLL in both loader
locations. Only the Box64 text, unified INI and a game-local `dxvk.conf` are
changed.

| Package | Change | Risk |
| --- | --- | --- |
| `perf35-cpu-global.zip` | `FASTNAN=1`, `FASTROUND=1`, `BIGBLOCK=3`, `STRONGMEM=0` globally; `SAFEFLAGS=2`, `X87DOUBLE=1`, `CALLRET=0` retained | High; may recreate startup or math faults |
| `perf35-cpu-quiet.zip` | Keeps Box64 compatibility flags, disables PERF17 code capture, limits DXVK compiler workers to 1 and disables device-local constant buffers | Low; may only improve contention/stutter |

The global package is the first high-impact CPU test. It applies the same
flags that PERF33 used only for newly translated PES text to the whole process.
If it fails to boot, restore the PERF34 current package immediately. Do not
change `SAFEFLAGS` or `X87DOUBLE` in this test.

## Test

Use CPU 1728 MHz, GPU 768 MHz, RAM 1600 MHz, 1280×720 and the same match.
Close with **HOME → X → Close** before changing packages. Run each package at
least twice; the first run may warm the DXVK state cache. Keep the logs and
compare sustained moving gameplay after kickoff, not menus or a stationary
throw-in. A 30 FPS limiter is intentionally absent: it cannot create frames
while the translated game thread is below 30.

These are experiments, not a 30 FPS claim. If the global policy does not move
the sustained result toward 30, the remaining work needs a targeted Box64
dynarec build or game-side draw-call/quality reduction rather than another
DXVK version swap.
