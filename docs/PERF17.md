# PERF17 — scoped guest block experiment

**Superseded by [PERF17B](PERF17B.md).** The supplied hardware run rejected
the live-header identity check, so no experimental blocks activated. See
[PERF17-RESULT.md](PERF17-RESULT.md). The description below records the
original package; the original ZIPs remain unchanged.

This is an experimental CPU optimization on the stable PERF15 runtime,
motivated by the [PERF16 samples](PERF16-RESULT.md). It has not yet been
tested on Switch. No FPS improvement or 30 FPS result is claimed.

The stable boot/mapping/exception fixes and ABI4 remain. DXVK 3.1.1 is
restored after the WineD3D comparison. The package preserves the game,
saves, settings.dat, controller mappings and installed PERF13 ntdll.

## Change

After the first successful Vulkan present, newly translated blocks starting
in four measured EXE areas use BIGBLOCK=1. This permits Box64 to include
nearby control-flow paths in one translated block, potentially reducing
dispatch and register-state transfers. The global Compatible profile stays
BIGBLOCK=0, SAFEFLAGS=2, FASTNAN=0, FASTROUND=0, STRONGMEM=1, X87DOUBLE=1,
CALLRET=0. No global math or memory-ordering setting is relaxed.

Selected VAs: `0x112f000–0x112ffff`, `0x937000–0x937fff`,
`0x93b000–0x93bfff`, `0x93c000–0x93dfff`. These cover the PERF16 sampled
instruction buckets, not identified function boundaries. Forward extension
is capped at the selected range's end. All other block entries retain the
baseline policy. Previously compiled blocks are not invalidated merely to
apply this experiment; if they were compiled before the first present,
they remain baseline until naturally recompiled.

The selector checks the loaded EXE header at its fixed image base 0x400000.
The first 512 bytes must match fingerprint `0x4e46d440` (FNV-1a). Unknown
headers fall back to baseline. This is a version check, not an authenticity
or security boundary. The local reference EXE SHA256 is
`329fa5fb45e4087352c8ba783b0dfa5e44823ba4168c3acccddc02f73daf1820`.
No executable is included or modified.

Earlier whole-process BIGBLOCK experiments did not demonstrate a 3D fix.
This experiment is narrower and based on the now-stable PERF15 baseline;
its performance effect must still be measured. If `selected`/`completed`
stay zero, the optimization was not applied and FPS cannot be used to
judge the selected policy.

## Small, bounded code capture

To identify the actual packed game instructions and generated ARM64 code,
the build also saves up to eight completed translations overlapping the
measured hot instruction windows (one baseline and one optimized slot per
area). Copies happen into fixed
buffers during compilation, with no file I/O, extra mutex, thread pause or
per-frame hook. The existing log thread writes each immutable snapshot once.
Capture is limited to 8 KiB guest + 8 KiB ARM64 per slot: at most 128 KiB of
raw code, approximately 400 KiB of formatted log. The ARM64 block may be
truncated; the log reports both original and captured sizes.

Continuous sampling and verbose tracing are off. There is still a small,
bounded capture/write cost, so compare frame rate after the code records
have been written. `perf17-capture.txt=0` disables capture for a clean
repeat benchmark. `tools/decode-perf17.py <log>` verifies and disassembles
complete records offline. Captures may include startup translations; their
recorded hash and block policy must be considered before attributing them
to a later scene.

## Install and test

1. Close the app with HOME → X → Close. Extract
   `pes13-perf17-hotblocks.zip` to the SD root, overwrite, and use the same
   forwarder targeting `switch/pes13-nx/pes13-nx.nro`.
2. Keep the same clock, 1280×720 setting, teams, stadium and camera. Check
   startup and 2D menus, then stay on player/team selection for 30 real
   seconds and in a match for 60 real seconds after kickoff.
3. Preserve `switch/pes13-nx/pes13-nx.log` after closing. Expect build marker
   `pes13-nx-0.2.0-perf17-hotblocks`, `[PERF17] hotblocks=1 identity=1`,
   nonzero `selected`/`completed`, and bounded `[PERF17-BLOCK]` / code records.
   The `[PERF8]` line still describes the unchanged global profile.
4. For an A/B control on the same new NRO, extract
   `pes13-perf17-control.zip`, which sets hotblocks=0 and capture=1. Restart
   fully and repeat the same scene. To enable again, reapply the main ZIP.

If boot, visuals, input or stability regresses, extract
`pes13-perf17-rollback.zip`. It restores the exact stable PERF15 NRO/ABI4
winebox64 pair and DXVK 3.1.1, with profiling and both PERF17 flags off.

## Validation

The host C fixture exercises range boundaries, pre-present/control/unknown
image fallback, exact preservation of every other environment field,
block-end clamping, snapshot quotas and truncation, immutable copies,
duplicate rejection, and one-shot reporting under ASan/UBSan. The existing
mapping and resume-gate checks also run during the WSL build. The builder
restores baseline source files in its finally block. Packaging verifies
the NRO metadata/icon, stable ABI4 DLL hash, DXVK hash, configuration and
archive contents. Host tests do not execute generated ARM64 game code or
prove hardware compatibility/performance.
