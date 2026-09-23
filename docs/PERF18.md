# PERF18 — avoid redundant rounding-mode writes

This experiment follows the [PERF17B hardware result](PERF17B-RESULT.md).
The captured matrix routine has 143 FPCR save/setup/restore groups. PERF18
skips the two FPCR writes in a group when current and requested rounding
modes already agree. It keeps the original rounding and restoration when
they differ. Arithmetic precision, NaN handling and all global Compatible
options remain unchanged; FASTROUND stays 0 and X87DOUBLE stays 1.

The change is limited to x87 D8/DE arithmetic and D9 float stores in four
captured EXE address ranges, after binding the supported file identity.
SSE, other game functions, DLLs, and transcendental/native-helper calls
keep their original behavior. There is no per-operation C call, counter,
file I/O or log. The conditional branches execute inside generated ARM64.

Unlike PERF17 BIGBLOCK, this can affect the matrix routine's first
compilation, before the first present. The package disables the BIGBLOCK
experiment and keeps bounded snapshots, no continuous profiler. An ARM64
snapshot may truncate after 8 KiB; metadata records the actual block size.

## Install

1. Close with HOME → X → Close.
2. Extract `pes13-perf18-roundguard.zip` into the SD root and overwrite.
   Keep the existing forwarder: there is still only
   `switch/pes13-nx/pes13-nx.nro`.
3. Keep the same clocks, teams, stadium and graphics settings. Stay on the
   3D team selection screen for 30 real seconds, then play for 60 seconds.
4. Preserve `switch/pes13-nx/pes13-nx.log` before the next run.

Expected build: `pes13-nx-0.2.0-perf18-roundguard`. The log should contain
`[PERF18] roundguard=1 identity=1` and nonzero `emitted_sites` and
`matrix_sites`. Those count generated sites, not calls or saved CPU time.
`[PERF17] hotblocks=0` is intentional. Snapshots still use PERF17 tags.

For a comparison with the same NRO, extract `pes13-perf18-control.zip`,
close fully and launch again. This disables the rounding guard and keeps
bounded capture. Restore the main package to turn it on again.
`pes13-perf18-rollback.zip` restores the exact stable PERF15 NRO/ABI4 pair
and DXVK, with experiment flags off. No package changes the game EXE,
saves, settings.dat, controller mapping, ntdll or global Box64 preset.

## Validation and limits

`tests/perf18_round.py` compiles an emitter fixture using the real pinned
Box64 ARM64 macros and the new helper. Unicorn executes old and new ARM64
for 8,832 cases: all 16 host/guest rounding combinations, FZ/DN settings,
multiply/add/double-to-float conversion, special values and seeded random
bits. Results, FPSR, NZCV and FPCR restoration match bit for bit. Equal
rounding uses zero FPCR writes, differing rounding uses the original two.
Disabled and out-of-range emission is byte-identical to the baseline.
These are semantic checks, not Switch performance measurements.

ASan/UBSan policy tests cover the identity/scope gates and counters, plus
the previous mapping, resume and preset regression checks. The builder
uses generated copies of three Box64 files and checks the vendor checkout
remains unchanged. Packaging checks the NRO/icon, ABI4, DXVK and archives.

There are no hardware results for PERF18 yet. Its branches also cost CPU
time, and frequent rounding mismatches may erase the benefit. This does
not establish a 30 FPS target, nor exclude other CPU or driver bottlenecks.
