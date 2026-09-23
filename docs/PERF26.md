# PERF26 — guarded native returns

This is a hardware experiment for CPU dispatch overhead, based on the sampled
PERF25 result. It has not yet demonstrated a Switch FPS gain or fixed the
reported slowdown after events. A locked 30 FPS is not established.

## Install and compare

1. Save the current logs, then HOME → X → Close the game.
2. Extract `pes13-perf26-callret.zip` to the SD root and overwrite. There is
   one NRO, `switch/pes13-nx/pes13-nx.nro`; use the existing forwarder.
3. Keep the same teams, stadium, camera and 1280×720 graphics, with CPU 1728 /
   GPU 768 / RAM 1600 for this comparison. Play for roughly five real minutes,
   including a lofted ball, replay and foul/goal, then ordinary play for at
   least 30 seconds. Note the real time since launch when a slowdown begins.
4. Preserve `pes13-nx.log` and all four `pes13-nx.previous-*.log` files before
   further launches rotate them. The build marker is
   `pes13-nx-0.2.0-perf26-callret`. After the first present, `[PERF21]` should
   show `CALLRET=2`; `[PERF8]` retains the global `CALLRET=0` baseline.

The main package disables the CPU sampler in both profile settings. Buffered
ten-second counters and the existing bounded snapshots remain. It changes no
game files, saves, settings.dat, controller mapping, renderer or clock setting.

For an A/B comparison, `pes13-perf26-control.zip` changes only the new
`perf26-callret.txt` option to 0, keeping the same PERF26 NRO and sampling off.
Fully close and relaunch after changing it. Reapply the main ZIP to enable it.
If stability regresses, `pes13-perf26-rollback.zip` restores the exact PERF25
NRO and quiet configuration.

## What changes

Newly translated blocks in the existing post-present game-text scope use
`CALLRET=2`. Box64 can retain a native return target instead of always resolving
the guest return through the jump table. Mismatched targets take the existing
fallback. Level 2 retains return-site guards for code invalidation; the
Horizon trap handler rechecks guest code or exits the stale block.

Startup, DLLs (including rld.dll), excluded matrix page and blocks translated
before the first present retain the global preset. No existing block is forcibly
invalidated. Selection happens once at block entry under the translator mutex;
the environment remains immutable across the four emission passes. Mixed
optimized and baseline calls can fall back, limiting possible gains.

SAFEFLAGS=2, STRONGMEM=1, BIGBLOCK=0, FASTNAN=0 and the established math policy
(scoped FASTROUND=1, X87DOUBLE=1) remain. The prior matrix, guard-fusion and
copy optimizations remain. Fusion already rejects blocks with callret metadata.
The existing 64 KiB native call-stack limit and dirty-code trap are retained.

## Validation

The policy test checks file identity, startup and address exclusions, immutable
selection, control mode, scope limits and an otherwise identical environment.
The actual pinned return-emitter body and existing stack-cap encoders are
executed in 816 Unicorn cases covering matched/mismatched returns and bounded
pushes. Nine host trap tests cover clean/changed/unreadable/gone code,
always-test blocks and invalid sites. The actual trap body is used, with mapping,
hash/cache and OS operations stubbed.

These tests do not cover concurrent code modification on Switch, all floating
point cache/purge states or whole-game execution. Integration on hardware is
still required. The return fixture omits unchanged memory/flag barriers and
uses have_purge=0; these limitations are recorded in `callret-tests.json`.

The generated native translator and opcode sources must match PERF25 exactly.
All 13 math sources must match PERF24. Verification checks final linked hooks,
all three retained stack caps, header dependency tracking, NRO metadata,
ABI4 DLL hashes and source restoration. Build in WSL without Docker:

```
PES_BUILD_ROOT=/home/blekjek/pes13-build python3 tools/build-perf26.py
PES_BUILD_ROOT=/home/blekjek/pes13-build python3 tools/verify-perf26.py
python3 tools/package-perf26.py
```
