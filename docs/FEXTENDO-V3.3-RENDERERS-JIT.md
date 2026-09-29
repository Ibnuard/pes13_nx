# FEXTendo v3.3 — renderer choices and cold JIT trial

App version **0.3.4**, build `pes13-fextendo-renderer-jit-v1`.
This is a test candidate, not a confirmed Switch stutter fix.

## Install

Requires the working FEXTendo core3 installation used for the GPLAsync test.
Close the application, then merge **only the root `switch/` folder** from
`pes13-fextendo-v3.3-renderers-jit128-v1.zip` into the SD root. Replace the NRO
and FEX module together. Existing game files, saves, graphics selection,
music preferences and `configuration.ini` are not included or overwritten.

The NRO path remains `switch/pes13-fex/pes13-fex.nro`. A forwarder that opens
this path can be reused. A forwarder embedding an NRO needs to be rebuilt.

Settings now has two renderer entries below Background music:

- **DXVK 3.1.1** — default when no selection has been saved.
- **DXVK 2.7.1 async** — the unmodified Ph42oN GPLAsync v2.7.1-1 x86 DLL.

Selection is saved in `launcher/renderer-choice.txt`. The main thread installs
the chosen pair of DLLs and matching configs while the launcher draws its
loading screen. Both DLL locations, both configs and the installed-version
record change as one recoverable transaction before any guest code starts.
An interrupted transaction is rolled back on the next launch. Missing or
invalid profile files prevent game launch. Unchanged files are verified but
not rewritten. Graphics presets retain the selected renderer's config.

Bundled profiles live in `launcher/renderers/dxvk-3.1.1/` and
`launcher/renderers/dxvk-2.7.1-async/`, each containing `d3d9.dll` and
`dxvk.conf`. Neither profile adds game data.

## CPU experiment and comparison

Two changes target the CPU translation path itself:

- With FEX disk cache disabled and no code-map writer, skip the image metadata
  lookup (including its shared ImageTracker lock) previously performed for
  every cold compile. The disabled cache lookup call is also skipped. Source
  tests execute the real gates: 10,000 modeled cold compiles avoid all 10,000
  unnecessary image lookups/cache calls. This measures removed operations,
  not Switch FPS or the fraction of compile time they consumed. Cache ON,
  code-map collection, debug naming, SMC validation and invalidation keep
  their required metadata paths.
- The included `fex_jit_small` flag selects **128 guest instructions per FEX
  compilation block**, compared with the previous 500. The FEX module accepts
  128 only for the existing fast profiles. Multiblock compilation, memory
  ordering settings, self-modifying-code tracking, thread affinity, VSync and
  graphics quality remain as before. No shader or JIT disk-cache improvement
  is claimed by this change.

The intention is to shorten individual cold compilations and limit work on
code beyond the path currently being executed. Smaller blocks can also
increase dispatch/compilation count and reduce warm performance, so this
must be evaluated on hardware. It is a latency experiment, not evidence
that total CPU work has already fallen.

1. For comparison with the latest log, select **DXVK 2.7.1 async** first
   (the untouched default is 3.1.1). Keep OC, preset, teams, stadium and camera fixed.
   Enable Debug timestamp. Record kickoff, first shoot and long-ball stutters.
2. Play a second match without closing the app. Save the log after both.
3. To isolate the JIT change, copy `control-jit500/switch/` to the SD and repeat
   with the same renderer. This keeps the metadata optimization/new UI/runtime
   and selects the previous 500-instruction cap. Reapply the root `switch/` to return to 128.
4. Renderer comparison is then available directly in Settings; use a fresh
   application launch per run and change only one variable at a time.

INI values take precedence over standalone flags. If already present, set
`fex_jit_large=0`, and set `fex_jit_small=1` for the candidate or `0` for the
control. Do not change other INI options for this comparison.

Expected log: `[FEXTENDO-RENDERER] selected=... verified=1`, the corresponding
DXVK version, and **both** `[FEX3-JIT-LAUNCH] maxinst=128` and
`[FEX3-JIT-CONFIG] maxinst=128`. The control should report 500 in both places.
Async should additionally report `dxvk.enableAsync = True`. Some first-use
draws still cannot use the upstream async path; it does not precompile FEX
CPU code. Missing/late objects should be recorded as well as frame stutters.

`rollback/switch/` restores the exact previous core3 NRO/FEX module and the
previous GPLAsync DLL/config pair. Save user-customized configs separately
before rollback. The optional new renderer profile folders may remain.

## Latest log findings

Reviewed capture: 1,724,658 bytes, SHA-256
`94ded50ce5cfeacf41b73b60f70448b9841dc38f515b1c6489baaeafa9dc74a9`.

- GPLAsync 2.7.1-1 and `dxvk.enableAsync = True` are confirmed. One compiler
  worker is configured; `dxvk-cs` is offloaded to zero-based core 3.
- Heavy `gameThread` TID 160 is on zero-based core 1, with sampled utilization
  around 79–83%. A UI labeling cores from 1 would call this CPU 2.
- At Play-relative **T+106.171–111.064**, that thread records **1,655 FEX
  compilations and 2,769,760 microseconds of aggregate compile wall time**.
  These are many calls across a window, not one 2.77-second freeze. Wall time
  includes scheduling and is not a direct CPU-cycle measurement.
- Shader-worker TID 28 has a wait spanning approximately **T+96.619–138.558**.
  Therefore active shader compilation does not explain all the overlapping
  cold-game-thread activity. Later heavy game threads have much less cold
  compilation. This supports targeting CPU translation alongside rendering.
- The capture totals 36,035 `compile_code` calls / 30.97 seconds cumulative
  wall time, peak 57.716 ms. Native pipeline measurements total 708 calls /
  4.00 seconds, seven over 50 ms, peak 404.008 ms. Different threads and nested
  measurements can overlap; these totals must not be added as lost frame time.
- 449 gaps over 50 ms were recorded, with 107 dropped records. The largest
  gap is 718.604 ms and includes startup/loading context. These are not all
  gameplay stutters. Overlay was disabled in this capture; times above are
  reconstructed from the recorded Play-origin tick.

Reported GPU 99% may matter during fast camera movement, but it does not
prove that GPU execution causes the first-match freezes. The largest sampled
gaps have short measured native acquire/submit/fence work; that does not
measure every GPU queue or the CPU work upstream of Present. The evidence
supports a cold CPU-compilation experiment, not declaring the GPU irrelevant.

The old Sarek NONE capture has a higher recorded pipeline cost, but the two
captures are not matched scenes/runs. No percentage improvement is inferred.

## Verification and attribution

Host ASan/UBSan tests cover renderer selection, both actual bundled DLLs,
graphics-preset interaction, unchanged-file verification, invalid/missing
assets, 11 rename failures, 6 failed SD flushes and 11 interrupted transaction
points. Launcher tests use the production C renderer and controller loop.
Linked ARM64 tests cover the retained thread, wait, pipeline and diagnostic
paths. Tests check all three JIT caps and all eight small/large/disk flag
combinations, plus the exact cold-compile metadata gates. The package binds
check results to the final ELF/FEX hashes.
These checks do not substitute for Switch execution.

FEX is upstream **FEX-Emu**; the Horizon/Switch port and this profile/launcher
integration are FEXTendo work by **AndroSwitch Project / Ibnuard**. Wine-NX
and Autorun remain the attributed runtime base/reference. DXVK 3.1.1 and
Ph42oN GPLAsync DLLs are upstream binaries, not project-authored renderers.
See `THIRD_PARTY.md` and the included license/source evidence.
