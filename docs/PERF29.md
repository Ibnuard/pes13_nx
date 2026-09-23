# PERF29 — measured worker block growth

**2026-09-22 hardware report:** the first supplied PERF29 run develops severe
match stalls with reported repeated audio/video. Worker block growth is not
recommended for normal play. Use the same-NRO control, not another preset.
See [results and control instructions](PERF29-RESULT.md). Host tests below did
not establish whole-game correctness.

This is an experimental CPU translation change based on the PERF28 samples.
It is not a demonstrated 30/60 FPS result or a fix for the startup crash.
The measured baseline remains roughly 15–19 successful presents/s in match.

## Install

1. Close the game with HOME → X → Close. Extract
   `pes13-perf29-worker-blocks.zip` onto the SD root and overwrite.
2. Keep the forwarder at `sdmc:/switch/pes13-nx/pes13-nx.nro`. There is one NRO,
   with its embedded icon and title **PES13-NX PERF29**.
3. Keep the same teams, stadium, camera, 1280×720 preset and clocks for the
   comparison. Play five real minutes, including a lofted ball, foul and replay.
   Note whether normal play recovers after the replay.
4. Copy `pes13-nx.log` and all available `pes13-nx.previous-1.log` through
   `previous-4.log` before more launches rotate them. A successful load is
   needed before judging match performance; the recurring boot crash remains
   unresolved.

The main package disables the CPU sampler in both configuration layers. It
keeps periodic aggregate metrics and the bounded fault capture. It adds no
per-frame SD trace. The expected marker is
`pes13-nx-0.2.0-perf29-worker-blocks`; `[PERF29] worker_blocks=1` confirms the
experiment is enabled. `selected` and `completed` count translations, not
executions or saved CPU time.

## Optional comparison packages

| ZIP | Use |
| --- | --- |
| `pes13-perf29-control.zip` | On the same PERF29 NRO, disables only worker block growth; CPU sampling remains off. Fully close and relaunch. |
| `pes13-perf29-sampling.zip` | Enables worker block growth and the existing bounded CPU sampler for deeper diagnosis. Requires the PERF29 NRO. |
| `pes13-perf29-rollback.zip` | Restores the exact PERF28 diagnostic NRO/configuration, including its sampler. |

Reapply the main package to return from either control or sampling mode.
Use main versus control for an A/B comparison; rollback has different sampling
settings. Optional overlays contain no NRO. Main and rollback each contain
exactly one. None contains game executables, assets, settings.dat or saves.

## What changes

Box64 `BIGBLOCK=1` permits conservative branch block growth, instead of the
global `BIGBLOCK=0`. It is selected only for newly compiled blocks whose start
is in one of these half-open guest ranges:

```
00920000–00950000
01100000–0112f000
01130000–01150000
01170000–011b0000
```

The guest identity must match and at least one successful Vulkan present must
have occurred. Each selected environment is immutable through all four compiler
passes. Range ends cap forward extension at page boundaries. Existing compiled
blocks are retained; there is no forced invalidation or live global preset
mutation. First present is a gate, not proof that all game startup work is over.

The matrix page, observed startup-fault function, DLLs and global/pre-present
environment retain their previous selection. SAFEFLAGS=2, STRONGMEM=1,
FASTNAN=0, X87DOUBLE=1, scoped FASTROUND=1/CALLRET=2 and startup CALLRET=0 remain.
The PERF25 copy fingerprint accepts the new environment without changing its
emitter. The native renderer, targeted server notifications and fault capture
are unchanged from PERF28.

Larger blocks may reduce dispatch/state-transfer work, but can also increase
translation time and code size. This remains an A/B experiment, not a measured
gain. Broad BIGBLOCK changes were not promoted from earlier experiments; these
regions are chosen from the current worker samples after the earlier math fixes.

## Validation and build

ASan/UBSan tests cover actual pinned Box64 environment structures, scope
boundaries, boot/control/unknown-image exclusions, immutable four-pass choice,
retained copy fingerprint and startup capture, and exact option preservation.
Final verification checks linked ARM64 hooks, unchanged math/copy emitters,
renderer/fault sources, pinned Box64 vendor and byte-identical source restoration.
These are host/build checks, not whole-game execution tests.

Build in WSL without Docker:

```
PES_BUILD_ROOT=/home/blekjek/pes13-build python3 tools/run-perf29-build.py
python3 tools/package-perf29.py
```

The durable build driver snapshots mutable sources before starting and records
completion in `local/perf29/build-status.json`. Do not launch simultaneous
runtime builds against the shared source tree.
