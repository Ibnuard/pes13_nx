# PES13 Low Window v3 — live settings and loading diagnosis

Version **0.3.9-lw3** is a targeted diagnostic update, not a verified fix for
accelerated movement or long prematch loading. Normal Launch keeps diagnostic
capture disabled. No ZIP, NSP, kernel, game DLL, preset, or clock change.

## Install and test

1. Close PES with HOME → X. Copy `switch/` to the SD root, replacing only
   `/switch/pes13-fex/pes13-low-window.nro`.
2. Use the same **PES13 Low Window** HOME tile and **FEXTendo Memory v1 TEST**
   boot entry as LW2. This NRO update needs no additional reboot or forwarder.
3. Select **Debug launch**. Confirm `0.3.9-lw3` in the startup banner. Keep
   preset, renderer and clocks unchanged for comparison.
4. Play through the on-field prematch wait and kickoff; make a few fast/long
   passes. Preserve `switch/pes13-fex/fex-runtime.log` after closing and note
   approximately when prematch and kickoff occurred.
5. Binary rollback is the exact LW2 NRO in `rollback/switch/`.

Existing controller bindings, saves, settings files and Kitserver files are
preserved. The normal launcher still applies the established VSync-on,
Frame-Skipping-off and XInput-on policy before starting the game.

## Reference-file result

The user's two 852-byte files have valid WECF version-2 headers and CRCs:

| User label | Flags | Frame Skipping bit | XInput flags |
| --- | --- | --- | --- |
| OFF from PC | `0081` | clear | clear |
| ON from Switch | `0289` | clear | set |

Only offsets 12–15 differ: the checksum and flags `0x0208`. This result does
not invalidate the reported 2× movement or the user's checkbox operation; it
means the saved pair does not contain an OFF/ON difference in that checkbox.
The reason for the UI/file discrepancy has not been established.

The actual Settings.exe supplied by the user (SHA-256
`761eb6873dafc3fc7cec27b82eff66e36e7ec99b87af5e024a8b535edc52c705`)
provides an independent oracle. Its English resource maps TEXT_ID_126 to
“Enable Frame Skipping”; control 0x451 calls the original setter at 0x41be20.
Executing that x86 setter under Unicorn confirms that it changes `0x0002`.
For example `0289` becomes `028b` when checked and stays `0289` when unchecked.
The `0x0008` setter belongs to the XInput/DirectInput radio handlers. No
settings bits were redefined from the filename labels or the initial diff.
The audit tool modifies neither the EXE nor either source .dat file.

## Why another diagnostic build

The patched executable reports file version 1.3.0.0. LW2's optional timing
object reader was fingerprinted only for the original 1.0 image. Its absence
of live reports cannot establish the patched game's effective flags or speed.
LW3 adds read-only WECF candidates for 1.00, 1.03 and 1.04. It checks header,
size, plausible fields and header stability before reporting values. CRC
validity is reported separately because the game can change a loaded value.
Unsupported/unmapped results are repeated, so one dropped startup message
does not silence the whole diagnostic run. No observer writes into the game.

The 1.03/1.04 candidate addresses derive from SCREEN_WIDTH minus the verified
WECF width offset in the Kitserver reference:
[lodmixer_addr.h](https://github.com/NiklasOff/kitserver/blob/main/src/lodmixer/lodmixer_addr.h).
Clock-call sites are observed without executing or modifying them:
[speeder_addr.h](https://github.com/NiklasOff/kitserver/blob/main/src/speeder/speeder_addr.h).
The adjacent QPC location is labelled a candidate. An unrecognized opcode
remains unknown; it is never treated as proof of a clock multiplier.

The new device log is SHA-256
`55fe9ae5da967fba29b9d93ef61eb09ef283e36e402cfa3c66234c19f4248823`,
ending at 420.360 seconds. The file callback worker, tid 84 in this run, spends
near one core through much of 130–200 seconds. At 198.863 seconds the preceding
ten-second SD window reports zero reads, and the shader-creation window is
also zero. That does not prove the callback's exact hot function; it shows
that SD throughput or shader compilation alone does not explain this period.
The user's on-field prematch interval has not yet been timestamp-correlated.

## New log lines and interpretation

- `[LW3-LIVESET]`: the game's loaded flags, dimensions and quality. Compare
  these with `[SETTINGS-VERIFY]`, which reads the files before launch.
- `[LW3-CLOCKSITE]`: observed original/modified clock-call opcode and target,
  every 30 seconds for a recognized WECF layout. No rate inference by itself.
- `[LW3-VKWORK]`: six largest completed Vulkan-call wall-time totals, grouped
  by OS thread handle and operation stage, every five seconds. The fixed RAM
  table reports overflow. Match the thread to `[WAIT-CPU]` to distinguish
  work reaching the graphics driver from other CPU work. Wall time includes
  waits and scheduling, and is not GPU execution time or CPU sampling.

The hexadecimal `code` field groups the existing Vulkan probe stages:
`0` acquire, `1` present, `2` submit, `3` fence wait, `4` semaphore wait,
`5` graphics-pipeline creation, `6` compute-pipeline creation, `7` memory
allocation, `8` image creation, `9` buffer creation, `a` shader-module creation,
`b` device idle, `c` queue idle. Related API variants share a stage; this is
not an individual function identifier. Match native handles with the thread
profiler's handle-to-Wine-tid mapping before assigning them to named workers.

Existing frame, pipeline, shader and SD counters remain. Presents are not a
measurement of unique frames or simulation speed. The optional gameplay.dll
still fails attach with c0000005 at about 13.1 seconds in the supplied run;
that does not prove it causes subsequent movement issues. No third-party
plugin is disabled automatically.

## Verification and limits

The package carries source, build hashes, Settings.exe oracle results,
ASan/UBSan host results and tests of the actual ARM64 ELF under Unicorn.
Tests cover short/unsupported/stale-CRC live reads, no guest writes,
concurrent bounded counters, normal-launch diagnostic silence, real Debug
capture, prior memory preflight/cleanup, and preset transaction rollback.
The Switch GPU, real match speed and loading-time improvement cannot be
validated by these local tests. Hardware retesting is required.
