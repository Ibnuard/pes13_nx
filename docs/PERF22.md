# PERF22 — scoped x87 float optimization

PERF21 is the hardware-tested fallback. PERF22 tests one additional Box64
option in the same game-code scope: `X87DOUBLE=0`, allowing the translator
to keep x87 values as floats when its analysis permits. It retains double
operations where needed; it does not force every operation to float.
See [PERF21's measured result](PERF21-RESULT.md) for the captured conversion cost.

| Option | Startup/DLLs/excluded pages | PERF21 control game code | PERF22 game code |
| --- | ---: | ---: | ---: |
| FASTROUND | 0 | 1 | 1 |
| X87DOUBLE | 1 | 1 | **0** |
| SAFEFLAGS | **2** | **2** | **2** |
| FASTNAN | 0 | 0 | 0 |
| STRONGMEM | 1 | 1 | 1 |
| BIGBLOCK | 0 | 0 | 0 |
| CALLRET | 0 | 0 | 0 |

The normal Box64 config explicitly retains the Compatible baseline. The new
selector makes a private copy of the PERF21 environment; it never mutates
global settings during execution. `perf21-fastmath.txt=1` is required, and
`perf22-floatmath.txt=1` enables the new step. Setting only the latter to 0
restores the PERF21 policy on the same NRO.

The [pinned Box64 documentation](https://github.com/ptitSeb/box64/blob/2f130fab1d6e1a4ee8a71dc60cfdfcc839ad192a/docs/USAGE.md#box64_dynarec_x87double)
defines 0 as using float where possible and 1 as always using double for x87.
Allowing lower precision can change arithmetic results. This is a performance
experiment, not a bit-identical optimization. Player motion, ball physics,
replays, camera movement and menus need hardware testing as well as FPS.
Local validation does not establish a gain or stable 30 FPS.

## Scope and implementation

The existing PES13 image identity must match. Selection begins after the first
successful Vulkan present, only on newly compiled full `.text` pages from
`0x401000` to `0x13d1000`. The matrix page `0x112f000..0x1130000`, the packed
entry section and DLLs remain excluded. Already-compiled startup blocks keep
their original settings; no forced invalidation is added. Block extension is
bounded exactly as in PERF21. No helper runs in guest execution for selection.

The 13 generated ARM64 emitter files retain all 146 per-block FASTROUND reads.
The additional X87DOUBLE read for `FLD float` in `dynarec_arm64_d9.c` and the
two native compilation precision-policy checks now also use `BOX64DRENV`.
Each generated opcode file is compiled in all four passes. Box64's existing
float/double cache propagation, promotion, spills and branch handling perform
the translation; this patch does not hand-rewrite their register types.
The vendor checkout remains untouched.

PERF19's exact matrix patch and PERF20 fusion remain enabled. Memory-ordering,
CALL/RET, SAFEFLAGS, the stable boot fixes, DXVK and the ABI4 DLL are retained.

## Install and compare

1. HOME → X → Close. Extract `pes13-perf22-floatmath.zip` into the SD root and
   overwrite. Launch the same `switch/pes13-nx/pes13-nx.nro` forwarder.
2. Keep the same OC, 1280×720 settings, teams, stadium and camera. Spend 30 real
   seconds at 3D team selection, then at least 60 real seconds in a match. Include
   one replay; note approximately when it starts and whether motion looks normal.
3. Preserve `switch/pes13-nx/pes13-nx.log` before restarting.
4. For a controlled comparison, apply `pes13-perf22-control.zip`, close fully and
   repeat the same sequence. It disables only X87DOUBLE=0, retaining FASTROUND=1.
   Reapply the main package to enable PERF22 again.

Expected build: `pes13-nx-0.2.0-perf22-floatmath`. After activation, the new
`[PERF22]` line should show `enabled=1 active=1 game_X87DOUBLE=0 FASTROUND=1
SAFEFLAGS=2`, with completed translations increasing. In control mode it shows
`enabled=0 active=0 game_X87DOUBLE=1 FASTROUND=1` after PERF21 activation.
`[BOX64]`/`[PERF8]` still describe the global baseline, and `[PERF21]` describes
the retained fallback environment. Use `[PERF22]` for this experiment's values.
Initial reports before option initialization contain zero/default fields;
inspect the later periodic reports.

The main/control packages have verbose logging and continuous sampling off.
The same eight bounded capture slots remain available to compare generated code.
In main mode, baseline blocks compiled before activation cannot consume them.
Compilation counts are not execution counts or measured time saved.

`pes13-perf22-rollback.zip` restores the exact hardware-tested PERF21 NRO and
enables its FASTROUND policy. `pes13-perf22-diagnostic.zip` is an optional
flag-only overlay for the 10 ms sampler; leave it off for main/control FPS tests.

Packages preserve saves, settings.dat, game data, controller mappings and ntdll.
There is one NRO in main/rollback, and no NRO in flag overlays. No game executable
or game assets are included.

## Local validation

- ASan/UBSan checks cover identity, first-present gating, DLL/matrix/packer
  exclusions, unchanged SAFEFLAGS/global/PERF21 environments, block bounds,
  control fallback and completed-translation reporting.
- The retained PERF19/20 patch checks and boot/mapping/resume checks run during
  the build. Their earlier equivalence checks do not imply equivalent arithmetic
  for X87DOUBLE=0.
- Generated emitter changes are limited to the option lookup macros. The build
  verifies the 13 files in all four passes and both native policy lookups.
- WSL compilation, restored source bytes, NRO title/icon, ABI4/DXVK/rollback
  hashes, archive contents and manifest round trips are checked before delivery.
