# PERF25 — targeted copy-loop experiment

This build targets a measured guest copy loop and keeps PERF24's renderer,
ABI4, scoped FASTROUND=1, X87DOUBLE=1, SAFEFLAGS=2, memory-ordering settings,
scheduler and log history. It is not yet a verified Switch FPS improvement.
It does not fix the startup null-read crash; it captures evidence for that crash.

## Install

1. Keep the current logs before further launches rotate them away.
2. HOME -> X -> Close. Extract `pes13-perf25-paircopy.zip` into the SD root and
   overwrite. It contains one NRO at `switch/pes13-nx/pes13-nx.nro`; use the same
   forwarder. No game files, saves, settings.dat or controller mapping are included.
3. Keep CPU 1728 / GPU 768 / RAM 1600, the same teams, stadium, camera and graphics
   for the comparison. Test ordinary play, a fast lofted ball and a replay, then
   continue normal play for at least 30 real seconds. Note approximate real time
   after launch for a drop, and whether it recovers. Do not delete caches.
4. Copy `pes13-nx.log` and all available `pes13-nx.previous-*.log` files from
   `switch/pes13-nx/` before launching again. The history also retains failed boots.

The build marker is `pes13-nx-0.2.0-perf25-paircopy`.
`[PERF25] paircopy=1 accepted=...` confirms that the guarded emitter was selected.
Counts are translation-pass checks, not runtime executions. Actual use still
depends on pointer alignment and count. Missing acceptance can also mean that
the block compiled before the post-present environment was available.

## Optional controls

- `pes13-perf25-control.zip`: after the main package, copy this small overlay to
  disable only pair-copy. CPU sampling stays off. Reapply the main package to
  restore pair-copy. Use matching scenes for A/B comparison.
- `pes13-perf25-diagnostics.zip`: optional overlay enabling PERF24's bounded CPU
  sampler (2 seconds per 10, 20 ms interval) on the PERF25 NRO. Use only when
  further sampling is needed; the main package restores sampling off.
- `pes13-perf25-rollback.zip`: restores the exact PERF24 NRO with math-control
  and CPU sampling off. This preserves the same coarse frame measurements.

The main package retains `[FRAME24]` histograms and ten-second reports with
buffered SD writes. No per-copy logging, runtime allocation or function call is
added to the executed fast loop. Translation selects the optimization once per
emission pass, using an environment chosen at block entry so a first-present
transition cannot change its instruction size between passes.

## Scope and validation

Only REP MOVSD at guest `0x0093df43`, with all 35 surrounding routine bytes
matching the hardware capture and the known PES image identity, is eligible.
Forward, even, eight-byte-aligned copies transfer two dwords at a time. Backward,
odd or unaligned copies use the existing scalar loop. An aligned pair cannot
cross a 4 KiB protection boundary. Overlapping buffers preserve the original
sequential copy behavior under these restrictions.

Host replay uses the actual pinned Box64 opcode encoders. The baseline bytes
must equal the loop captured from the Switch. The baseline, new ARM64 loop and
x86 REP MOVSD are compared in 2,173 scenarios, including 30 page faults,
overlap, direction and alignment. Actual PERF15 fault recovery is exercised.
Unrelated registers, SIMD state and flags remain unchanged. Pinned upstream
signed bit-pattern shifts are excluded from UBSan shift instrumentation in
the encoder fixture; the vendor itself is not modified.

Build and verification run in WSL without Docker:

```
PES_BUILD_ROOT=/home/blekjek/pes13-build python3 tools/build-perf25.py
PES_BUILD_ROOT=/home/blekjek/pes13-build python3 tools/verify-perf25.py
python3 tools/package-perf25.py
```

The verifier checks all four compiled emitter passes, the final linked hooks,
unchanged math emitters, source restoration and the pinned clean Box64 tree.
Build with the account that owns the prepared build tree. Existing artifacts
are retained. Host tests do not replace validation on a real Switch.
