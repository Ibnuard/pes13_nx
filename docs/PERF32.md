# PERF32: larger game translation blocks on the PERF25 base

The target is **above 30 FPS during kick-off match play**, with sustained
performance after replays and events. This candidate has not been tested on
Switch and that target is **not yet achieved or verified**.

## Change

PERF32 enables Box64 `BIGBLOCK=3` only for newly translated ordinary PES text
after the first successful present and a matching game identity. It allows
larger translated regions even when they overlap older blocks. This aims to
reduce dispatch and register/state transfer between small blocks. Startup,
DLLs, the separately optimized matrix page, the known startup lookup region
and sections outside the selected text retain their prior environment.

SAFEFLAGS=2, X87DOUBLE=1, STRONGMEM=1 and CALLRET=0 remain. The established
scoped FASTROUND=1, matrix fusion and copy changes remain. Selection is fixed
for every translation pass, including copy-gate decisions; global settings
are never changed underneath running guest threads. Existing validation and
code invalidation stay enabled. Larger blocks can cost more compilation time
and code memory, so this requires hardware testing rather than assuming it
will improve every scene.

The base is PERF25. PERF26 native-return optimization, PERF27 wait routing,
PERF29's policy, and PERF31's driver polling/timing are not included. There is
no renderer switch, audio-buffer change, forced frame limiter or clock change.
This single CPU experiment cannot guarantee a 30 FPS match.

## Packages: each includes exactly one NRO

- `pes13-perf32-game-blocks.zip`: primary test, block growth on, CPU sampling off.
- `pes13-perf32-control.zip`: same NRO, block growth off; PERF25 policy for comparison.
- `pes13-perf32-diagnostics.zip`: same candidate and NRO, CPU sampling on in
  two-second bursts each ten seconds; use when the primary still slows down.

Fully close PES from HOME, then merge the chosen package's `switch` folder
into the SD root and replace files. The forwarder remains
`sdmc:/switch/pes13-nx/pes13-nx.nro`. All packages preserve game data, saves and
settings.dat. They are upgrades for an existing installation, not base installs.
Unlike the old quiet overlay, every variant replaces the executable.

Check `[BUILD] pes13-nx-0.2.0-perf32-game-blocks` in the new log. The main test
also reports `[PERF32] base=PERF25 CALLRET=0 worker_blocks=1`, followed by
`scoped_BIGBLOCK=3`. `ready`, `selected` and `completed` confirm the policy
was used during translation; they are not execution counts or FPS estimates.
`[PERF21] BIGBLOCK=0` describes the parent environment and is expected.

## Match test

Keep the comparison scene, resolution and clocks unchanged (last reported:
1280x720, CPU 1728 / GPU 768 / RAM 1600 MHz). Note roughly when kick-off starts
relative to application launch. Test normal play, a lofted ball, replay and
foul/goal transitions. Continue beyond **six real minutes since launch**;
the previous failure began after minute five. After a drop, allow another
30–60 real seconds so a report captures it before closing.

Save the current log and available previous logs before another launch rotates
them. If the main build still drops, the full diagnostics package helps locate
the busy translated code and native waits. Sampling can affect timing, so its
results are not an uninstrumented FPS benchmark. The control package is a
single-variable comparison; reapply the full main package to re-enable growth.

## Validation

Build with `python3 tools/run-perf32-build.py` in WSL and package with
`python3 tools/package-perf32.py`. Tests check the actual pinned Box64
environment, identity/bounds/startup exclusions, immutable four-pass policy,
copy normalization and capture delegation under ASan/UBSan. Verification
checks actual linked hooks, unchanged math/copy emitters, retained component
objects, stock Mesa linkage, source restoration and NRO/icon/ZIP integrity.
These checks cannot validate whole-game correctness or measure console FPS.
