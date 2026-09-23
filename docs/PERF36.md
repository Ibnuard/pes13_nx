# PERF36 — honor scoped FASTNAN in ARM64 emitters

This package uses the PERF34 current-DXVK baseline and changes the runtime NRO.
It fixes a mismatch between the PERF33 per-block configuration and the code
generator: eight SSE/AVX emitter files read global FASTNAN even when the block
has its own override. They now use the existing per-block environment accessor.
Blocks without an override still use the global value. No new text flags are
required; the unified INI and game settings remain the same.

Global FASTNAN=0, SAFEFLAGS=2, X87DOUBLE=1, existing startup gates and the PERF33
game-code address scope remain unchanged. This avoids enabling relaxed math in
all DLLs. It does not fix the separately observed startup null-pointer fault or
image mapping conflict, and it does not claim 30 FPS yet.

## Validation

`tests/perf36_fastnan.py` takes real scalar SSE emission fragments from the pinned
Box64 source and executes their ARM64 output in Unicorn. Across 19,000 input,
rounding-mode and flush-to-zero cases, finite results compare identically; NaN
results remain NaNs. Untouched vector lanes, input registers, FPCR and NZCV are
checked. The fallback cases produce byte-identical code. NaN payload/sign and
FPSR equivalence are deliberately not asserted; FASTNAN relaxes those semantics.

For the arithmetic fragments alone, ADDSS/MULSS/SUBSS/DIVSS shrink from 14 to 2
ARM instructions, SQRTSS from 7 to 2. This excludes opcode decoding, loads and
the rest of the guest block, and is not a whole-game speedup factor. Packed SSE
and AVX sites are wired by the same accessor replacement but are not covered by
this scalar execution fixture. Build verification checks all eight files across
all four dynarec passes and compares generated object code against PERF34.

## Install and compare

Close PES13-NX with HOME → X → Close. Copy the ZIP's `switch` folder to the SD
root and overwrite its included files. Keep game data, saves and caches. The
main package contains the runtime and baseline configuration/DLL overlay, not
the game or saved settings. Use the same 1728/768/1600 clocks and 1280×720.

Compare moving gameplay with the same teams, stadium and camera for at least
six minutes after kickoff, including a replay and corner. Test two fully closed
launches and retain their logs. A stationary throw-in and the menu are not
equivalent workloads. If visual or physics behavior changes, restore
`pes13-perf34-dxvk-current.zip`. The optional diagnostics package uses the same
NRO and enables sampled profiling; assess its FPS separately from the quiet
package because sampling adds work.

No Switch hardware result is included. The target remains at least 30 FPS in
moving gameplay, and it has not yet been verified.
