# FEX3 kick-off pacing experiment

The previous frame-pacing build reaches matches, but the tester still sees
pauses followed by apparent fast motion. This candidate tests less CPU
run-ahead and measures the native stages that were missing from the previous
log. It is an experiment, not a verified fix for simulation speed or a claim
of 30 FPS at stock clocks.

## Hardware evidence

Input: `local/fex3/kickoff-pacing/before/fex-runtime.log`, 92,497 bytes,
SHA-256 `d52a4ca3e048e25ae204bb19cf7e39e71ab33b84d784fda38f8c1418126c3a26`.
Reproduce the physical-time summary with `tools/analyze-fex-kickoff-pacing.py`.
The tester places kick-off after approximately two minutes and the OC-to-stock
change at approximately five minutes. The supplied frame series ends around
four minutes after the first report. Without a logged clock-change marker,
these estimates do not isolate the stock run.

DXVK confirms `d3d9.maxFrameRate=-1`, FIFO and three swapchain images. The
automatic software limiter is no longer engaged, but the symptom persists.
Several approximately ten-second windows contain about 600 successful host
presents. This does not prove 60 unique game frames or correct simulation
speed. In most of these windows the native present wrapper averages roughly
0.24-0.60 ms, and presentation-mutex wait averages below 1 microsecond. The
largest observed entry gap reaches 764 ms. Late windows drop to approximately
18-25 host presents/s. Time before the wrapper remains unresolved: game work,
translation, DXVK, acquiring images and waiting for previous GPU work can all
contribute. A short queue-present call does not exonerate the entire driver.

The clock audit finds matching 100 ns units and 10 MHz frequency in Wine's
normal QPC path. FEX's Windows raw-counter pseudo-op is guarded for ARM64EC,
not this WOW64 backend. No clock scaling change is justified by that code.
Self-suspend requests succeed without rejection; native heap failures remain
zero. These checks do not establish which part of the game catches up.

## Candidate

Only one behavioral setting changes from the previous package:

```
d3d9.maxFrameRate = -1
d3d9.maxFrameLatency = 1
```

In [DXVK 3.1.1](https://github.com/doitsujin/dxvk/blob/v3.1.1/src/d3d9/d3d9_swapchain.cpp#L1061),
the second value lowers the frame-latency bound used by the synchronization
signal before the application continues. This tests whether shortening queued
work reduces visible catch-up bursts. It does not force a 30 FPS limit, reduce
the swapchain's image count, skip game updates or change time. Less overlap
may also lower throughput; the device must establish the trade-off.

The NRO retains previous present histograms and adds `[FEX3-PIPE]` summaries:

- `acquire_driver`: host image-acquisition calls.
- `submit_driver`: host QueueSubmit/QueueSubmit2 calls.
- `fence_wait` / `semaphore_wait`: host waits from Wine's native Vulkan thunks.
- `shared_clock_gap`: intervals between updates to Wine's shared clock page.

All measurements are CPU wall time. Waits include intentional parking and
scheduling, not just GPU work. Failed and timed-out calls still contribute to
their timing histograms; their result counts are separate. Bucket bounds and
since-launch peaks are identical to the prior `[FEX3-PACE]` observer. Five
stage lines and one integrity line follow each ten-second present report,
including after the first five minutes. Driver arguments, timeouts, return
values and clock values stay intact. The hot paths do no file I/O, allocation,
sleep, extra lock, thread pause or per-frame stack sampling.

FEX/DXVK/ntdll binaries, the Fastest configuration, real self-suspend, graphics
quality and save files are unchanged. The successful self-suspend checkpoint
and previous frame-pacing folder remain available.

## Install and acceptance test

Copy `dist/pes13-fex3-kickoff-pacing/switch` to the SD root after HOME -> X,
overwriting the five supplied files. Use the existing `pes13-fex.nro` forwarder.
This package is a directory, with no ZIP and no game data or saves.

Verify build `pes13-fex3-kickoff-pacing` and effective
`d3d9.maxFrameLatency = 1` in the log. Keep CPU/GPU/RAM settings fixed for the
whole run. Stock settings can be tested as a separate run from application
startup. Play five minutes after kick-off, including fast passes, a set piece
and a replay. Record whether pauses and apparent double speed persist, plus
their approximate time since startup. Preserve each log before restarting.

If the one-frame queue is worse, set only `d3d9.maxFrameLatency = 0` in
`drive_c/PES13/dxvk.conf`, restart, and compare the same scene/clocks. This
restores the previous queue policy with the same measurement NRO. Do not
change the automatic limiter at the same time.

Local validation covers observer buckets, failed/timeout calls, shared-clock
units, unchanged driver calls, sanitizer tests, linked ARM64 self-suspension,
native/FEX ABI, packaging hashes and the checkpoint identity. These are local
checks; Switch frame pacing and simulation behavior remain unverified.
