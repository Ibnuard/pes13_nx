# PERF13 results: less suspend polling, separate startup allocation failure

Two logs were copied before the user replaced the shared log path:

- `local/perf14/perf13-first-launch-bad-alloc.log`: 47,254 bytes,
  SHA256 `6aa695841c1d6ee5ba03b88e8ded33db9cc9d321331a0aec0dc037b342f840d6`.
- `local/perf14/perf13-success-match.log`: 61,089 bytes,
  SHA256 `7b24b7c508ed8506939b2bc2de6688573968b50f00cb0f5d9ce36263cbbcc1c5`.

The user confirms success/failure can alternate between full HOME -> X ->
Close launches without a console reboot. In the successful run, 2D feels
substantially lighter, team selection improves but remains under ~10 FPS,
and a match lasting one in-game minute still looks roughly 5 FPS.

## Successful run

The intervals ending at 40/50 seconds record 49.98/48.62 presents per second.
The 70–110 second intervals record 5.68–8.89, and the final five intervals
(ending at 130–170 seconds) record 5.39–5.79. Screenshots are not timestamped
against the log, so these are intervals consistent with the user's sequence,
not precise automatic scene classification or a full matched benchmark.

In those final intervals, main thread 4 uses 83–87% of a core, thread 176
95–97%, thread 124 77–87%, and thread 72 about 3–4%. Thread 176 starts at
the same executable entry routine 0x4da0e3 as other game workers. That does
not identify the worker's actual function, nor exclude driver work called
from it. Total CPU use is approximately 3.05–3.11 cores.

Suspend requests are 7,232–7,905 per ten-second interval, versus roughly
318,000–338,000 in PERF12's late team-selection intervals. The scenes differ,
but the fall in polling and thread 72 occupancy is consistent with the
backoff working. Thread 124 remains busy in match; the existing counters
cannot say whether its remaining work is useful execution or another loop.

Host-present calls average under 1 ms in these final intervals; this measures
the host call, not full GPU execution. CPU sampling in the 3D scene is the next
step for attribution. Earlier loading samples are not evidence about the new
busy thread 176. No 30 FPS match claim is supported.

## Failed startup

This run is an actual process exit, despite the loading image remaining:
`terminate called after throwing an instance of 'std::bad_alloc'`, followed
by main-thread exit code 3 and `[EXIT] parked after self-terminate`.
Loader-lock timeouts from other threads follow the main-thread exit; they
are not the first failure in this log. CPU use then falls to ~0.10 cores.

Several HMAP fixed replacement attempts fail their unmapped-range check with
EEXIST at 0x03720000 and 0x03920000 before termination. The successful log
also has EEXIST failures at other addresses. Thus a single HMAP warning does
not prove the cause of bad_alloc, and the failed allocation's call stack and
size are still unknown. bad_alloc alone does not prove physical RAM exhaustion.

Early reserved space also differs: the failed run has 508 MB total / 155 MB
largest range, the successful run 455 MB / 293 MB. Layout changes between
launches; more total reservation does not necessarily mean a larger contiguous
usable allocation. These numbers alone cannot explain strict alternating runs.

Code review identified three intervals where guest reservations could be
temporarily exposed to native allocation. PERF14 tests a narrow fix for those
intervals, independently of Box64 settings, DXVK or shader-cache contents.

