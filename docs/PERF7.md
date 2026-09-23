# PERF7 post-initialization turbo experiment

**Superseded by PERF8.** The hardware log from 2026-09-19 contains no post-init
profile activation marker, so the staged optimization described below was not
verified to execute. PERF6/7's diagnostic-counter removal also accidentally
made a real mutex lock conditional; PERF8 repairs it. The historical build
recipe is retained for reproducibility. The mixed menu/gameplay FPS interval
below does not establish a controlled performance improvement.

PERF6 boots reliably and raises its first measured interval to 1,143 Vulkan
presents in 60.163 seconds, about 19 FPS averaged across menus and gameplay.
The log still shows a fully occupied CPU core during 3D rendering, while SD
reads and the 456-shader cache are healthy.

PERF7 keeps the PERF6 fast four-level Box64 jump table, final `-O1` compiler
optimization and removal of diagnostic atomics. It also preserves PERF3's
ARM64 fast-suspend `ntdll.dll` and all seven Compatible values byte-for-byte.

The new optimization has two stages:

1. Boot, `rld.dll` initialization and the path up to WineVulkan use Compatible
   settings. This retains the condition that fixed `rld.dll failed to
   initialize`.
2. After `winevulkan.dll` attaches successfully, only newly translated blocks
   use `SAFEFLAGS=1`, `FASTNAN=1`, `FASTROUND=1`, `BIGBLOCK=1` and
   `STRONGMEM=0`. `X87DOUBLE=1` and `CALLRET=0` stay unchanged. Previously
   translated protection code is not rebuilt.

The overlay also places `dxvk.conf` beside `pes2013.exe` with
`d3d9.maxFrameRate = -1`. This disables DXVK's CPU-side software limiter that
warned about poor frame pacing. Vulkan FIFO still caps presentation to the
display refresh rate.

Close PES through HOME, extract the complete `switch` directory to the SD
root and overwrite files. It does not contain the game, settings or saves.
Use the same forwarder. Confirm the log contains:

- `pes13-nx-0.2.0-perf7-post-init-turbo`
- `[BOX64] post-init game profile`
- `[PERF7]`
- no `Built-in frame rate limiter enabled` warning

Test at the same safe CPU, GPU and RAM clocks, teams, stadium and camera used
for PERF6. Keep a match running beyond 120 seconds before closing through
HOME; the second report includes per-thread CPU load. If `rld.dll`, gameplay
logic or rendering regresses, restore `pes13-perf6-overlay.zip`.

Build in WSL:
`PES_BUILD_ROOT=/home/blekjek/pes13-build python3 tools/build-perf7-test.py`.
