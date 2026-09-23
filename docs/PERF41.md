# PERF41: one matrix-sibling throughput experiment

PERF40 improved perceived match speed on Switch. Its exact early FASTROUND
block was selected and the earlier 114 rounding guards disappeared, while the
remaining slow-match intervals still use nearly three CPU cores. See
`PERF40-RESULT.md` for the measured limits.

PERF41 keeps PERF40 enabled and lets only a second, measured x87 matrix block
(`0x112f8f0`, 232 guest bytes) use the same per-block FASTROUND environment.
Its guest bytes must match the captured fingerprint. The translation is capped
before the adjacent matrix block. The existing PERF19 patch for `0x112fb90`,
global SAFEFLAGS=2, X87DOUBLE=1, DXVK and the rest of the configuration stay
unchanged. No game executable bytes are modified. `perf41_matrix_round` in
`configuration.ini` controls this new path.

Install `pes13-perf41-matrix-round.zip` at the SD root and fully close/reopen
the game. Test the same clocks, resolution, teams and stadium as PERF40. The
package is quiet (`profile=0`, `perf17_capture=0`). Save `pes13-nx.log` after a
match run. Its build marker should be `pes13-nx-0.2.0-perf41-matrix-round`.
`[PERF41] selected=1` means the candidate block was compiled with FASTROUND;
`fingerprint_rejected=0` means its bytes matched. The separate PERF19 line
should still say `applied=1 rejected=0`.

For an on/off comparison using the same NRO, install
`pes13-perf41-control-overlay.zip` after the main package. It changes only
`perf41_matrix_round=0`; PERF40 remains enabled. Close and reopen, then repeat
the same match. Reinstall the main package to restore PERF41.

FASTROUND relaxes x87 rounding fidelity, so this is a guarded experiment. The
host test checks fingerprint rejection, matrix page boundaries, PERF40 and
PERF19 isolation, and preserved global Box64 options. It does not establish
gameplay correctness or a 30 FPS lock on hardware.
