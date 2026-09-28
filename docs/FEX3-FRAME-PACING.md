# FEX3 frame-pacing candidate

The self-suspend checkpoint now reaches matches. The tester reports good FPS
but intermittent pauses shorter than a second, followed by apparent fast
motion during kick-off. This candidate addresses one observed source of
extra scheduling work; it does not claim that every pause or speed change
has been fixed on hardware.

## Evidence and change

The input is `local/fex3/frame-pacing/before/fex-runtime.log`, SHA-256
`4eec022d7fc2c7289f2473a9bd70bf2c7237b486488df5411d574f46faee9b62`.
It identifies `pes13-fex3-self-suspend`, DXVK 3.1.1 and Vulkan FIFO. Recorded
self-suspend requests succeed, with no allocation failure in the native heap.
The last progress interval contains 3,373,024 `NtQueryPerformanceCounter`
calls (native syscall 0x31). The log has no per-frame timing distribution,
so it cannot locate the reported sub-second pause or prove actual 2x
simulation speed. Several five-second windows approach 60 Vulkan presents
per second; those are host submissions, not a measurement of unique game
frames or simulation speed.

DXVK explicitly activates its automatic frame limiter after detecting a
short window around 84 FPS. Its
[3.1.1 sleep implementation](https://github.com/doitsujin/dxvk/blob/v3.1.1/src/util/util_sleep.cpp)
finishes waits by polling the high-resolution timer. This is an additional
translated CPU wait, although the log does not attribute every timer call
to DXVK. The older Box64 packages shipped `d3d9.maxFrameRate = -1`; the FEX
integration packager omitted that configuration.

This package restores that setting in `drive_c/PES13/dxvk.conf` and explicitly
selects the file through the guest's `DXVK_CONFIG_FILE` environment variable.
DXVK's
[D3D9 implementation](https://github.com/doitsujin/dxvk/blob/v3.1.1/src/d3d9/d3d9_swapchain.cpp#L1045)
skips its automatic limiter for this value. The application's presentation
interval and the native FIFO path remain responsible for synchronization.
No guest timer is scaled, no game executable is patched and no fixed delay
is injected into suspend/resume. DXVK, FEX and ntdll DLL bytes, graphics
quality, Fastest settings and the real self-suspend fix match the checkpoint.

## Native measurements

The rebuilt NRO measures entry-to-entry intervals, total native presentation
time, presentation-mutex acquisition time and the host driver's queue-present
call. `[FEX3-PACE]` summaries are emitted from the existing log flusher about
every ten seconds throughout the run. The frame path only reads the physical
counter and updates in-memory statistics: no file writes, allocation, sleep,
extra mutex or thread sampling.

Histogram upper bounds in microseconds are 8334, 16667, 20000, 33334, 50000,
100000, 250000, 500000, then overflow. `gap50_then_lt8` counts a gap of at
least 50 ms followed by one shorter than 8 ms on the same thread/queue/
swapchain. It is a burst indicator, not proof of game-clock acceleration.
Peaks are explicitly since launch. Concurrent updates may straddle a report;
cumulative deltas preserve totals. `elapsed_ms` starts at the first diagnostic
report; `window_ms` uses real physical ticks rather than a flusher-loop count.
The first report has `window_ms=0` and is not an FPS sample.

These are CPU-observed Vulkan call timings, not scanout timestamps. Long
entry gaps with short native calls indicate time spent before this wrapper
(including game code, translation, DXVK work/waits and image acquisition).
Long driver calls or lock waits separate native presentation stalls. Smooth
call timing with visible game jumps points to a different simulation/input
timing problem and must not be called a solved FPS issue.

## Install and test

Close PES through HOME -> X. Copy the package's `switch` folder to the SD
root and overwrite all five files. Continue using
`switch/pes13-fex/pes13-fex.nro`. No ZIP is produced. Game data and saves are
not included. The working `pes13-fex3-self-suspend` checkpoint is preserved.

Verify build `pes13-fex3-frame-pacing` and DXVK's effective
`d3d9.maxFrameRate = -1` in the new log. Play the same kick-off for at least
five minutes with unchanged clocks; include quick passes, a corner and a
replay. Save the log after a pause/jump. Note approximately when it occurred
and the CPU/GPU/RAM clocks. If the game runs continuously too fast with this
setting, change only `d3d9.maxFrameRate` to `0` and restart: this restores the
previous automatic limiter with the same diagnostic NRO for comparison.

## Local validation

- WSL devkitA64 build and NRO icon/NACP validation.
- Shipping observer replay: 500 ms gap then 5 ms burst, bucket boundaries,
  stream changes, failed/suboptimal presents, idle reporting and 200,000
  concurrent samples under AddressSanitizer/UndefinedBehaviorSanitizer.
- Linked ARM64 self-suspend handler: eight modeled wait/transport scenarios.
- Matched native heap/FEX interface and real typed profile getters.
- Package hashes, unchanged DLLs/INI and archived checkpoint verification.

The device must establish whether removing the additional limiter improves
the reported pauses. Native observer tests do not measure Switch FPS.
