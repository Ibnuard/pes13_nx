# PERF28 — PES13-NX targeted diagnostics

This is an evidence build based on PERF27, **not a new FPS optimization or a
claimed startup fix**. The target remains smooth match play, first sustaining
30 FPS and evaluating whether 60 FPS is achievable. Neither target is proven.
The measured PERF27 match segments are around 15–19 presents/s.

## Install and test

1. Close PES with HOME → X → Close. Extract
   `pes13-perf28-diagnostics.zip` to the SD root and overwrite.
2. Use the same forwarder, `sdmc:/switch/pes13-nx/pes13-nx.nro`. There is one
   NRO. The log build marker must be `pes13-nx-0.2.0-perf28-diagnostics`.
3. If startup fails, preserve its log. Close fully and retry; once it starts,
   spend approximately 30 seconds in team selection, then play five real
   minutes with a lofted ball, replay, and foul/goal. Continue normal play
   after replay for at least 30 seconds. Note approximate elapsed real times
   for those events so samples can be associated with the scene.
4. Copy `pes13-nx.log` and the available `pes13-nx.previous-1.log` through
   `previous-4.log` before extra launches rotate them. Keep the same resolution,
   teams, stadium, camera and clock settings across comparisons.

Start with diagnostics. Optional `pes13-perf28-quiet.zip` changes only the
two profiler settings on the same NRO. Apply it and relaunch to compare sampler
overhead after collecting evidence. Reapplying diagnostics enables sampling.
`pes13-perf28-rollback.zip` restores the exact PERF27 NRO/configuration.
These overlays contain no game EXE, game assets, settings.dat or saves.

## What changes

The native runtime uses the PES13-NX project name in its banner; Wine-NX,
Wine, Box64, DXVK, Mesa and other upstream attribution/licenses remain.
Internal ABI and configuration names are retained for compatibility.

CPU translation, all generated math/copy emitters, server notification
routing, renderer and game configuration stay at PERF27. SAFEFLAGS=2,
STRONGMEM=1, FASTNAN=0, BIGBLOCK=0, scoped FASTROUND=1/X87DOUBLE=1/CALLRET=2,
and global/startup CALLRET=0 remain unchanged.

The existing CPU sampler runs at 20 ms intervals for 2 seconds per 10 seconds.
It temporarily pauses sampled threads, so it can perturb frame timing and
its samples include blocked time. `[SAMPLE24]` records pause duration;
`[FRAME24]` distinguishes sampling windows. This is diagnostic mode, not a
production FPS benchmark. No per-frame SD trace has been added.

The new `[FAULT28]` capture runs once, only after the emulator returns an
access violation at the previously observed read-4 site. It checks the bound
PES image identity and exact runtime instruction bytes. It uses guarded guest
reads for caller/lookup code, the stack and a bounded inferred table scan.
Unreadable ranges, count overflow and excessive counts terminate or cap the
inspection; eight record read failures stop the scan. Only limited summaries
and sample records are logged. No guest memory, context or status is changed.

Table layout and ordering are hypotheses from captured instructions, not
established game structures. Other threads can mutate memory during capture;
this is not an atomic whole-process snapshot. The record cap is 2048. No match
in a capped/partially unreadable prefix does not prove a missing entry.
Capture occurs on the normal stack after emulator unwind, not inside the
native exception callback.

## Validation

Host tests use captured failing instructions, ASan/UBSan, oversized/wrapped
counts, unreadable memory, missing fingerprints, unchanged context, and eight
concurrent attempts at one-shot capture. Final verification checks linked
ARM64 hooks, identical PERF27 emitter/server sources, embedded NRO title/icon,
unchanged Box64 pin and byte-for-byte build-source restoration. These checks
do not substitute for a Switch run.

`python tools/decode-perf28.py LOG OUTPUT_DIRECTORY` extracts bounded runtime
code and disassembles the captured x86 caller/lookup with Capstone. It does
not execute the captured bytes; a partial/noncontiguous capture is not filled
with guessed data. Keep raw captures private with the other local game logs.

Build with WSL, without Docker:

```
PES_BUILD_ROOT=/home/blekjek/pes13-build python3 tools/build-perf28.py
PES_BUILD_ROOT=/home/blekjek/pes13-build python3 tools/verify-perf28.py
python3 tools/package-perf28.py
```
