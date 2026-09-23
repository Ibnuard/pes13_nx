# PERF19 — one rounding setup per captured matrix block

This follows [the PERF18 result](PERF18-RESULT.md). The goal is to remove
repeated setup work from a measured game-code hotspot while collecting
better evidence about remaining costs. It is an experiment, not a 30 FPS
claim or a demonstrated whole-game performance gain.

## Change and measured scope

For the exact matrix block at guest address `0x112fb90`, keep the first
x87 rounding-mode setup and last restoration. Size-preserving ARM64
branches bypass subsequent setup/restore groups. The arithmetic, order,
precision, memory accesses and register-cache operations stay intact.
Global Compatible settings remain unchanged, including FASTROUND=0,
X87DOUBLE=1, SAFEFLAGS=2 and STRONGMEM=1. Earlier BIGBLOCK and per-operation
PERF18 guards are disabled, so this experiment is isolated.

Only a 656-byte guest block with the captured fingerprint and its exact
7,064-byte ARM64 output are accepted. Blocks with secondary entries or
CALLRET records are rejected. Validation completes before any write,
before the existing instruction-cache flush and before publication.
Unknown/different output keeps the original translation. The on-disk EXE
is never modified. FNV fingerprints are version guards, not cryptographic
authentication. Changing compiler or emitter settings can disable this
optimization; the log records the rejection and observed fingerprints.

The executed body, measured by Unicorn before the common return lookup:

| Measure | Baseline | PERF19 |
| --- | ---: | ---: |
| ARM64 instructions | 1,760 | 703 |
| FPCR reads | 143 | 1 |
| FPCR writes | 286 | 2 |

This is a 60% reduction in instructions in **one routine**, not 60% lower
frame time. Branch cost, caches, other game workers, driver/GPU behavior
and the actual call frequency still determine the Switch result.

## Install and test

1. Close the game with HOME → X → Close.
2. Extract `pes13-perf19-matrix.zip` into the SD root and overwrite.
   Keep the existing single NRO and forwarder path:
   `switch/pes13-nx/pes13-nx.nro`.
3. Use the same clocks, teams, stadium, camera and settings as the prior
   test. Stay in 3D team selection for 30 real seconds and a match for 60.
4. Preserve `switch/pes13-nx/pes13-nx.log` before the next launch.

Expected build: `pes13-nx-0.2.0-perf19-matrix`. Look for `[PERF19] matrix=1
identity=1 ... applied=1 rejected=0` (applied can grow if recompiled).
These count successful compilation patches, not executions or saved time.
`[PERF17] hotblocks=0` is intentional; bounded code capture uses PERF17 tags.

If 3D is still slow, extract `pes13-perf19-diagnostic.zip` after the main
package and restart fully. Repeat a 60-second match, preserving the log.
This enables the existing sampler every **10 ms instead of 2 ms**, keeping
verbose logging off. It samples up to four previously busy threads and
reports instruction/module buckets, helping distinguish remaining game
code, native runtime/driver work and waits. Sampling perturbs execution
and includes blocked wall time; its FPS is not a clean benchmark.

`pes13-perf19-control.zip` disables the matrix patch on the same NRO and
turns sampling off. Use it for an on/off comparison in the same scene.
Reapply the main package to restore the optimization and disable profiling.
`pes13-perf19-rollback.zip` restores the exact stable PERF15 NRO/ABI4 pair.
Every package preserves game files, saves, settings.dat, controller mapping,
ntdll, the Compatible preset and the DXVK 3.1.1 graphics stack.

## Validation

- `tests/perf19_matrix.py`: entire captured old/new ARM64 blocks replayed
  in Unicorn for 1,728 cases across all host/guest rounding combinations,
  FZ/DN settings, finite/random/special inputs and output/input aliasing.
  Full guest memory, guest GPRs, floating register cache and FPCR/FPSR/NZCV
  match. `tools/perf19_plan.py` audits the complete straight-line body.
- `tests/perf19_patch.c`: ASan/UBSan checks identity, disabled/out-of-scope
  paths, short/different blocks, secondary entries, CALLRET rejection,
  changed code, repeated invocation and no partial writes on rejection.
  Its actual C-produced bytes equal the full-block tested ARM64 bytes.
- WSL build and prior mapping/resume/preset checks; NRO metadata/icon,
  ABI4/DXVK hashes and archive round trips. Original sources are restored.

The replay does not test Switch cycle timings, asynchronous faults/signals,
or full-game behavior. Native offsets remain unchanged, but hardware
stability and frame-rate impact still require a console test. The stable
rollback and same-NRO control are supplied for that reason.
