# PERF38: scoped x87 rounding-guard fusion

This is an unmeasured Switch performance experiment based on the PERF37
instruction samples. The 30 FPS gameplay target is **not yet verified**.

The new pass shares a rounding setup across compatible arithmetic operations
inside a straight-line region of a block, even if another region contains a
direct branch. It also recognizes the x87 memory-operand sequence with an
extra float-to-double widening instruction. Arithmetic instructions, operands,
rounding mode, guest addresses and native code offsets are preserved.

Scope is restricted to the measured guest math pages `0x112f000–0x1131000`.
The previously verified matrix patch at `0x112fb90` is retained unchanged.
Unknown images, 64-bit blocks, oversized blocks, secondary entries, CALLRET
metadata and unsupported branch/call patterns remain excluded. Every direct
branch destination is a fusion boundary. Unknown gap instructions also stop
fusion. The pass runs while a block is compiled, before executable publication;
it adds no per-frame hook or executed counter.

DXVK, the Box64 version, SAFEFLAGS=2, X87DOUBLE=1 and the existing scoped
FASTMATH/BIGBLOCK policy are unchanged from PERF36/PERF37. No game executable
or save is patched. This does not claim a startup-hang fix or a proven cause
for event-triggered slow motion.

## Install and compare

1. Close the application through HOME → X → Close.
2. Extract `pes13-perf38-region-fusion.zip` to the SD root, replacing its files.
   The executable remains `switch/pes13-nx/pes13-nx.nro`; the forwarder path
   does not change. Keep the game data, registry and saves.
3. Use the same CPU/GPU/RAM clocks, teams, stadium and graphics settings as
   the PERF37 test. Play at least 8–10 minutes, including replay, goal and corner.
4. Keep the resulting `pes13-nx.log` before another run rotates it.

The main package disables the intrusive CPU sampler and binary block captures;
lightweight periodic cadence and compilation counters remain. Its log marker
must be `pes13-nx-0.2.0-perf38-region-fusion`. `[PERF38]` reports how many guards
were actually merged, including separate counters for the two measured hot
blocks. Those counters do not measure executed frequency or FPS improvement.

For a control run with the same NRO, change only
`perf38_region_fusion=0` in `configuration.ini`, then fully close/reopen.
Use `1` to enable it again. This restores the PERF36 fusion behavior while
keeping logging settings identical, which is a cleaner comparison than a
different older NRO.

If the new counters show the hotspots were rejected or performance regresses,
the optional `pes13-perf38-diagnostics-overlay.zip` enables the existing CPU
sampler and bounded native-code capture. Use it for one diagnostic run only;
extract the main package again afterwards to restore quiet mode. It contains
configuration only, no second NRO. The two newly targeted snapshots include
the full native block, up to 16 KiB each.

## Validation and limits

The exact production C pass is exercised with AddressSanitizer/UBSan and
Unicorn. Tests compare guest memory, all GPR/vector registers, FPCR, FPSR and
NZCV across 7,680 baseline cases, 2,048 widening cases, 512 forward-branch
cases and 64 backward-loop cases. All four host and guest rounding modes,
flush-to-zero/default-NaN settings, special values and scratch variants are
covered. Capstone independently checks 6,000 branch displacements. Generated
bridge tests check image/scope rejection, matrix preservation and rollback.

Historical native captures show that the pass can remove additional guards;
those static counts are not an on-device speedup measurement. Some test
captures are outside this build's runtime scope. The current two hottest
blocks have not yet been captured in full, so `[PERF38]` counters are necessary
to establish coverage on the Switch. No guaranteed FPS increase is claimed.

The build verifier checks unchanged opcode-emitter machine instructions and
dispatch/preset sources against PERF36, restored WSL source files, and the
single NRO's title/icon. Remaining validation requires the actual Switch.
