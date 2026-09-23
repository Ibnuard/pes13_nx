# PERF40: fingerprinted early FASTROUND for one measured math block

The PERF39 diagnostic log captured the full native block at guest address
`0x113027b`. It still contains 254 ARM64 `MRS` and 394 `MSR` instructions
touching rounding state after PERF38 fused 114 guard sequences. The block is
inside the normal game FASTROUND scope, but its captured code is consistent
with the conservative pre-present environment. At roughly 120 seconds, when
the user reported a corner, measured presents fell from about 21/s to 18/s
and stayed near 16–20/s. The log has no scene marker, so the corner timing is
approximate. Host present time was generally below 2 ms while game worker
threads remained busy; this suggests a CPU-side experiment, not a confirmed
GPU driver fault.

PERF40 lets **only** the fingerprinted `0x113027b` block select the existing
per-block `FASTROUND=1` environment before the first successful Vulkan present.
Its 1,113 guest bytes must match the captured FNV-1a fingerprint. The pinned
matrix page, `rld.dll`, startup loader, other game blocks, SAFEFLAGS=2,
X87DOUBLE=1, DXVK, and PERF38 fusion policy are unchanged. No instruction is
patched in the game executable; the change affects compilation of that one
block. The optional flag `perf40_early_round` is read from `configuration.ini`.

Install `pes13-perf40-early-round.zip` at the SD root and fully close/reopen
PES13-NX. Keep the same CPU/GPU/RAM clocks, teams, stadium and settings. Play
past a corner and compare whether normal play remains at its earlier speed.
The package is quiet: `profile=0`, `perf17_capture=0`. Save the resulting
`pes13-nx.log` before another run rotates it. Its marker is
`pes13-nx-0.2.0-perf40-early-round`; `[PERF40] selected=1`
means the early translation used the candidate environment. A fingerprint
rejection leaves the established behavior intact.

For a same-NRO control run, install `pes13-perf40-control-overlay.zip` after
the main package. It changes only `perf40_early_round=0` in
`configuration.ini`. Close/reopen the application and repeat the same match.
Reinstall the main package to restore `perf40_early_round=1`.

FASTROUND relaxes x87 rounding fidelity, as it already does for ordinary
post-present game blocks. The fingerprint and exact address keep this
experiment narrow, but hardware gameplay and visual correctness still require
testing. This build does not claim 30 FPS or an event-trigger fix in advance.
