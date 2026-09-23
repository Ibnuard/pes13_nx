# PERF20 — fuse verified x87 rounding runs

This experiment retains the hardware-verified PERF19 matrix optimization
and extends rounding-setup elimination to other eligible game blocks.
See [the PERF19 console result](PERF19-RESULT.md) for the measured reason.
Switch performance and stability of the new pass still need a console test.

## Change

Box64's Compatible translation surrounds many x87 operations with a
rounding-mode setup and restoration. PERF20 recognizes the complete
pinned ARM64 emitter sequence and combines consecutive compatible guards
into one region. Arithmetic order, precision, loads/stores and the game's
rounding selection stay unchanged. The first setup and final restoration
remain; branches of the same size skip repeated work.

This runs once while compiling a block, before the existing cache flush
and publication. There is no extra C helper call or logging in executed
game code. No global FASTROUND/X87DOUBLE change is involved. The existing
boot fixes, controller behavior, DXVK version and Compatible preset remain.

The pass is deliberately restricted:

- Only 32-bit blocks inside the identified PES13 main image, up to 64 KiB
  of native code. DLLs and the existing exact PERF19 matrix block are excluded.
- Secondary-entry and CALLRET blocks are rejected.
- Any branch/call/return rejects the whole block except the final standard
  `BR x2` dispatch. No paths can enter the middle of a fused region.
- Each guard must match eight exact setup instructions, one supported
  scalar arithmetic instruction and the exact restore. Scratch-register
  variants cannot be merged with each other.
- Gaps allow only a small decoded set of guest memory operations, guest
  integer moves/adds, exact widening and FP moves/sign operations. Anything
  else ends the run, including narrowing, unguarded arithmetic, emulator
  state access, scratch-register access and unknown instructions.
- Code offsets stay unchanged. The game EXE is never patched on disk.

The FPCR governs conversions and rounding as described in Arm's
[instruction reference, FCVT](https://documentation-service.arm.com/static/6245c734b059dc5ff9a8bdab).
The only FP conversion allowed *between* guards is single-to-double
widening: its finite result is exactly representable. Narrowing and
arithmetic retain their original guard. FZ/DN behavior and sticky status
are included in replay tests; the pass changes only how often the same
rounding selection is installed/restored.

## Local validation

The actual production C pass is compiled as a host library and replayed
in Unicorn, rather than testing a separate Python rewrite:

- 7,680 complete runs across captured matrix/worker blocks and generated
  instruction sequences, all 16 host/guest rounding combinations, FZ/DN,
  special/random float values, mixed precisions, and guest memory aliasing.
  Full memory, all GPRs, all vector registers and FPCR/FPSR/NZCV match.
- Independent Capstone decoding checks the admitted memory opcode masks.
- ASan/UBSan checks bounds, template mutations, control-flow rejection,
  unsafe gaps, image/range/control guards and repeated invocation.
- The NRO hook's worker output must equal the replay-tested C output.

The captured six-store worker executes 87 → 52 instructions before its
common return lookup. FPCR reads fall from 6 → 1 and writes from 12 → 2.
These are block-local counts, not elapsed time or an FPS prediction. The
general pass is also exercised on the matrix capture, but the runtime
keeps the stronger exact PERF19 patch there.

Replay does not test Switch cycle costs, asynchronous faults/signals or
full-game execution. Native emulator-state aliasing by a guest pointer is
outside the supported guest ABI. Conservative rejection can substantially
limit coverage; the log counters expose that instead of assuming a gain.

## Install and measure

1. HOME → X → Close, then extract `pes13-perf20-roundfusion.zip` at the SD
   root with overwrite. Forward the same single file as before:
   `switch/pes13-nx/pes13-nx.nro`.
2. Keep clocks, 1280×720 settings, teams, stadium and camera unchanged.
   Spend 30 real seconds in 3D team selection and 60 real seconds in a match.
3. Preserve `switch/pes13-nx/pes13-nx.log` before restarting.

Expected build: `pes13-nx-0.2.0-perf20-roundfusion`.
`[PERF19] ... applied=1` confirms the matrix patch.
`[PERF20] fusion=1 identity=1 blocks=... merged=...` counts patched
compilations and removed guard pairs, **not executions or time saved**.
`flow_rejected`/`scope_rejected` are conservative fallback counts, not errors.

The main package disables continuous sampling and verbose logging. It
retains eight bounded code snapshots, written once by the log thread, to
capture the new hotspots. Their existing `[PERF17-BLOCK]` format is decoded
by `tools/decode-perf17.py`; slot/region now identify the eight PERF20
targets, with BIGBLOCK still zero. Each snapshot is capped at 8 KiB guest
and 8 KiB native code, with no file I/O inside the translator.

For a comparison, apply `pes13-perf20-control.zip` and restart fully. This
disables only the new fusion pass; PERF19 remains active on the same NRO,
with the same profile/capture settings. Reapply the main package to enable
fusion again. This is more comparable than contrasting old logs taken
with different profiling settings/scenes.

`pes13-perf20-rollback.zip` restores the exact previously tested PERF19 NRO
and its ABI4/DXVK files. `pes13-perf20-diagnostic.zip` is an optional flag
overlay for the PERF20 NRO that enables the 10 ms sampler if needed. Do not
use that overlay for the clean performance comparison. Reapply the main
package afterward to turn sampling off.

All packages preserve game data, settings.dat, saves, ntdll, controller
mapping and the global Compatible preset. The main and rollback archives
include one NRO each; the flag-only overlays include none.
