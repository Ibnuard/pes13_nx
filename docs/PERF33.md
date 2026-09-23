# PERF33 fastmath candidate

PERF33 is a measured follow-up to PERF32 for the PES13 Switch port. It keeps the PERF25 math, copy emitter, DXVK, Mesa NVK, audio and startup path. Only newly translated ordinary PES executable text after the first successful present receives the candidate Box64 environment:

- `BIGBLOCK=3`
- `FASTNAN=1`
- `STRONGMEM=0`
- `FORWARD=1024`
- `FASTROUND=1`, `X87DOUBLE=1`, `SAFEFLAGS=2`, `CALLRET=0` retained

This is intentionally scoped. It does not mutate the parent environment or rebuild already compiled blocks, and it does not change the renderer. `STRONGMEM=0` is the risky part: it may improve CPU throughput but can expose ordering bugs in a multithreaded game. If gameplay becomes unstable, use `pes13-perf33-control.zip` or restore the known-good PERF32 package.

## Packages

- `pes13-perf33-fastmath.zip`: candidate, block policy on, sampler off.
- `pes13-perf33-control.zip`: same NRO, only the PERF33 block flag off; this is the A/B control.
- `pes13-perf33-diagnostics.zip`: candidate with the existing two-second-per-ten-second CPU sampler. Sampling is for diagnosis, not an FPS benchmark.

All packages contain one complete `sdmc:/switch/pes13-nx/pes13-nx.nro` with the embedded icon and title **PES13-NX PERF33 FASTMATH**. They do not contain PES files, saves or `settings.dat`. Close PES with HOME then X then Close before replacing the entire `switch` folder payload.

## Test

Keep 1280x720 and CPU/GPU/RAM 1728/768/1600 MHz. First run the fastmath package and note the real elapsed time when kick-off starts. Test ordinary play, throw-in (ball held and then released), a lofted ball, replay, foul and goal. Continue at least six real minutes after kick-off. Save `switch/pes13-nx/pes13-nx.log` before another launch. The log should contain `[BUILD] pes13-nx-0.2.0-perf33-fastmath` and `[PERF33] ... FASTNAN=1 STRONGMEM=0 FORWARD=1024`.

The target remains above 30 FPS in kick-off match and is not guaranteed by this build. Host tests validate policy boundaries and linked objects only; they cannot predict Switch FPS.
