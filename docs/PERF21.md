# PERF21 — scoped FASTROUND experiment, SAFEFLAGS=2 retained

This follows [the PERF20 hardware result](PERF20-RESULT.md). It tests one
Box64 option with a clearer control than changing several flags together.
The new NRO has not yet been tested on a Switch; local checks do not
establish an FPS improvement or full-game stability.

## Exactly what changes

| Setting | Startup, DLLs, excluded regions | Eligible game blocks after first present |
| --- | ---: | ---: |
| FASTROUND | 0 | **1** |
| SAFEFLAGS | **2** | **2** |
| FASTNAN | 0 | 0 |
| X87DOUBLE | 1 | 1 |
| STRONGMEM | 1 | 1 |
| BIGBLOCK | 0 | 0 |
| CALLRET | 0 | 0 |

WAIT/DIV0 and every other runtime default remain unchanged. The normal
`pes2013.box64.txt` stays at the known Compatible baseline. The experiment
is selected with `switch/pes13-nx/perf21-fastmath.txt` (1 enabled, 0 control).

Unlike PERF19/20's redundant-work elimination, FASTROUND=1 **relaxes
rounding behavior**. It can produce different results in edge cases or
when the game selects a non-default rounding mode. Box64 documents this
tradeoff in its [pinned usage reference](https://github.com/ptitSeb/box64/blob/2f130fab1d6e1a4ee8a71dc60cfdfcc839ad192a/docs/USAGE.md#box64_dynarec_fastround).
Test player/ball motion, menus and visual correctness as well as FPS.
This experiment does not claim bit-identical arithmetic to Compatibility.

## Scope and implementation

The selection checks the existing PES13 image identity and applies only
to newly compiled blocks starting in `0x401000..0x13d1000`, the full pages
of the main `.text` section. It excludes the PERF19 matrix page
`0x112f000..0x1130000`, other executable sections (including the packed
entry section), data, and DLLs. The source PE's `.text` ends at
`0x13d11c1`; its last partial page is deliberately excluded.

Selection starts after the first successful Vulkan present. Startup
translations and already-compiled blocks retain their old settings.
There is no forced invalidation, live global-option mutation or extra
helper call in executed game code. The translator uses a separate,
immutable environment with only FASTROUND and its override markers changed.
Block-extension limits keep the profile away from excluded pages.

In this pinned Box64, ARM64 opcode emitters read FASTROUND with the
global-only `BOX64ENV` macro. Merely returning a per-block environment
would not activate the option. The build therefore generates copies of
the 13 affected opcode files, replacing only those FASTROUND reads with
Box64's existing `BOX64DRENV` macro. The checked-in vendor tree remains
clean. Every generated emitter is verified in all four compile passes.

The older broad PERF8/PERF17 selection is inactive in this NRO. The exact
PERF19 matrix optimization and PERF20 fusion remain available on baseline
translations. The matrix's excluded page retains the exact native code
required by its fingerprint. FASTROUND-generated blocks naturally contain
fewer of the guards targeted by PERF20.

`rld.dll`'s own code is outside the selected range (it loaded at
`0xfa390000` in the supplied run). This reduces startup exposure, but it
does not prove the game never calls sensitive main-image code later.
SAFEFLAGS has not been independently proven to be the setting that fixed
the historical `rld.dll` error. It stays at 2 throughout this experiment.

## Install and test

1. HOME → X → Close. Extract `pes13-perf21-fastmath.zip` into the SD root,
   overwrite, and launch the same `switch/pes13-nx/pes13-nx.nro` forwarder.
2. Keep OC, 1280×720 settings, teams, stadium and camera fixed. Stay at 3D
   team selection for 30 real seconds and in a match for 60 real seconds.
3. Preserve `switch/pes13-nx/pes13-nx.log` before restarting. Note any new
   initialization, ball/player movement, timing or rendering problems.

Expected build: `pes13-nx-0.2.0-perf21-fastmath`.
`[PERF21] enabled=1 active=1 selected=... completed=... game_FASTROUND=1
baseline_FASTROUND=0 SAFEFLAGS=2` demonstrates selection and completed
translations. The `[BOX64]`/`[PERF8]` baseline still says FASTROUND=0; that
is intentional. Counters are compilations, not executions or saved time.

The main package has verbose logging and continuous sampling off. Eight
bounded code snapshots are captured only from completed optimized blocks;
startup baseline blocks cannot consume them. Missing snapshots can mean
a target was already translated before activation. The control captures
baseline blocks for an on/off comparison.

`pes13-perf21-control.zip` disables FASTROUND selection on the same NRO
while retaining PERF19/20. Restart fully after applying. Reapply the main
package to enable the experiment again. `pes13-perf21-rollback.zip`
restores the exact hardware-tested PERF20 NRO. An optional
`pes13-perf21-diagnostic.zip` flag overlay enables the 10 ms sampler; use
the main/control packages without that overlay for the FPS comparison.

Packages preserve saves, settings.dat, game data, controller mapping and
ntdll. They restore the baseline Box64 configuration explicitly, keep the
same DXVK and ABI4 DLL, and contain one NRO in main/rollback (none in the
flag-only overlays).

## Validation

- ASan/UBSan policy checks: before/after-present behavior, image identity,
  game/DLL/packer/matrix boundaries, control mode, extension bounds,
  completed-translation counters, real `BOX64DRENV` behavior, unchanged
  global environment and SAFEFLAGS=2.
- The existing PERF19/20 patch checks and baseline boot/mapping/resume
  checks remain in the build. The new setting is not subjected to a false
  bit-identical arithmetic claim: it intentionally permits differences.
- Generated emitter changes are limited to the FASTROUND lookup macro;
  source hashes and four-pass compiler-command verification are saved.
- WSL compilation, NRO metadata/icon, exact ABI4/DXVK/rollback hashes and
  archive manifest round trips are checked before packaging.
