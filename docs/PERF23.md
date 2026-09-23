# PERF23 — secondary-core balancing and preserved launch logs

This follows the [PERF22 hardware report](PERF22-RESULT.md). The new NRO has
not yet run on a Switch. Host tests establish policy invariants and packaging
integrity, not an FPS gain or a fix for intermittent loading failures.

## Runtime change

The upstream balancer sorts measured thread loads and attempts to reduce the
busiest core. A separate busy worker can keep that maximum unchanged while two
other threads compete on a different core and another core is idle. The old
admission then rejects their redistribution.

With `perf23-balance.txt=1`, after the old admission is rejected:

- Consider only threads on a known single core, without game-fixed affinity,
  using at least 10% of a core in the measured interval.
- Move at most one thread. The source's remaining load must exceed the
  destination's old load by at least 15 percentage points. The resulting peak
  must not exceed the previous peak.
- Choose the move that most reduces the sum of squared core loads, retaining
  the existing allowed-core list and server-thread-following behavior.
- Apply no more than one such attempt every four seconds. The original
  balancer's decision and cadence otherwise remain unchanged.

`[BALANCE23]` logs successful secondary migrations, their thread IDs and cores.
The load-square metric is a scheduling score, not milliseconds or saved CPU.
`[AFF23]` records actual core masks and game-fixed affinity for the eight
busiest threads every ten seconds; `tid=mask/fixed` uses fixed=1 for a thread
the balancer must leave alone. A zero mask means the query failed.
No thread priorities or guest-visible CPU count are changed. Explicit game
affinity remains respected; this policy cannot improve a fixed-affinity case.

Math code is identical to PERF22: scoped FASTROUND=1 and X87DOUBLE=0, with
SAFEFLAGS=2 and STRONGMEM=1. Boot/guest-exception fixes, DXVK and the ABI4 DLL
remain intact. There is no new sampler or work on every rendered frame.

## Log history

At startup the runtime rotates these exact files in `switch/pes13-nx/`:

- `pes13-nx.log`: current run.
- `pes13-nx.previous-1.log`: most recent previous run.
- `pes13-nx.previous-2.log` through `previous-4.log`: older retained runs.

The oldest of the four retained logs is replaced on further launches. A
rotation error preserves the current file by appending rather than truncating
it; `[RUN23] rotation_errno` records this. A partial filesystem failure may
leave gaps in history. No saves, settings or cache paths are rotated.
Routine log buffering/flush cadence stays unchanged, so HOME closing can still
lose the final few seconds. The full stalled run should otherwise be retained.

The existing ten-second report emits `[WATCH23]` after two intervals with no
presents. This is a progress observation, not a deadlock detector: startup,
loading and background operation can also have no presents. It does not change
game behavior or automatically restart the game.

## Install and test

1. HOME → X → Close. Extract `pes13-perf23-transitions.zip` into the SD root,
   overwrite, then launch the same `switch/pes13-nx/pes13-nx.nro` forwarder.
2. If loading stalls, leave it for about 30 seconds so the existing heartbeat
   can record progress, then close/reopen normally. After up to four attempts,
   copy the current log **and all `pes13-nx.previous-*.log` files** before more
   launches replace the oldest records.
3. In a match, keep OC/settings unchanged. Play before and after one ball-out
   or goal-kick event, and continue for at least 30 real seconds after any drop.
   Note whether the slowdown recovers and preserve the logs.

Expected build: `pes13-nx-0.2.0-perf23-transitions`, with `[PERF23]
secondary_balance=1 history=4`. A `[BALANCE23]` line only appears when an eligible
migration succeeds. Its absence may mean no eligible contention was measured,
explicit affinity prevented movement, or the kernel rejected a move.

## Optional comparisons

- `pes13-perf23-control.zip`: disables only the new secondary balancing
  (`perf23-balance.txt=0`), keeping PERF22 math and log history on the same NRO.
- `pes13-perf23-math-control.zip`: keeps secondary balancing but restores
  X87DOUBLE=1 via `perf22-floatmath.txt=0`. FASTROUND=1 and SAFEFLAGS=2 remain.
  Use this if loading keeps failing; successful runs alone cannot establish
  causality, so keep the failed-run history too.
- `pes13-perf23-diagnostic.zip`: enables the existing 10 ms sampling profiler.
  This can affect performance; it is not needed for the first test.
- `pes13-perf23-rollback.zip`: restores the exact earlier PERF21 NRO, with
  FASTROUND enabled and X87DOUBLE=1. PERF21 does not retain launch history, so
  copy the logs before reverting.

The main package resets sampling/verbose to off and enables both PERF22 math
and secondary balancing. Reapply it to return from any comparison overlay.
Overlays require the PERF23 NRO and a full application restart. No game files,
saves, settings.dat or controller mapping are included or overwritten.

## Validation

WSL build without Docker. ASan/UBSan tests cover the secondary-core regression,
20,000 randomized layouts, fixed affinities, at most one migration, a
non-increasing peak and exact score reduction. Log rotation tests cover eight
launches, missing history, filesystem failure with append fallback and bounds.
The upstream profiler/balancer tests and the existing PERF22 compatibility,
matrix, locking, mapping and resume checks also run.

Generated math emitters and the native dynarec source must be byte-identical
to PERF22. Modified runtime/profiler sources are restored after the build.
Packaging verifies NRO metadata/icon, ABI4/DXVK hashes, baseline presets,
control toggles, exact PERF21 rollback and ZIP manifest round trips.
