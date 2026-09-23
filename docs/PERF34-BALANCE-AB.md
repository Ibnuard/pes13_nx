# PERF34 scheduler A/B overlays

The latest PERF34 run has a useful correlation around the persistent match
slowdown: a new PES worker (`start=0x4da0e3`) is created, then the normal core
balancer moves it from core 2 to core 3. The next ten-second window falls to
roughly 16 presents/s and stays around 18--20 presents/s. The log does not
contain game-scene markers, so this is a scheduler experiment, not proof that
the move itself causes the goal, replay, or corner event.

Both archives below contain the same PERF34 NRO, DXVK files, and Box64/math
preset. Only `configuration.ini` changes:

| Archive | Change | Purpose |
|---|---|---|
| `pes13-perf34-secondary-off.zip` | `perf23_balance=0`, `no_balance=0` | Keep the upstream balancer; remove only the PERF23 secondary migration. |
| `pes13-perf34-balance-off.zip` | `perf23_balance=0`, `no_balance=1` | Keep every worker on its existing affinity as a control for all migration. |
| `pes13-perf34-cache-ab.zip` | `gl_clean_test=1`, normal balancing | Alternate GPU cache cleaning every 30 seconds to test the post-replay present spike. |
| `pes13-perf34-gl-noclean.zip` | `gl_noclean=1`, normal balancing | Keep CPU cache cleaning disabled to measure the lowest-submit-overhead path. |

These are A/B overlays, not a claimed FPS fix. Test `secondary-off` first. If
the event drop remains, test `balance-off`; if that is worse, restore the
PERF34 config package or set `no_balance=0` and `perf23_balance=1` again.

The cache package is the next test after the two scheduler results. It keeps
`no_balance=0` and `perf23_balance=1`; only the NVK cache-clean path alternates.
It is useful when `[PERF8] host_present_ms_per_call` rises sharply after a
replay. Stop the test and restore the normal PERF34 configuration if the image
shows corruption or other visual errors.

`gl-noclean` is a separate, reversible measurement. It uses the same normal
balancing and math policy, but skips the CPU cache clean before every GPU
submission. This can lower submit overhead on the Switch, but it is not safe to
assume that every driver path remains coherent. Stop immediately if the image
shows corruption, missing geometry, or a hang. It is useful only if the log
shows a lower `host_present_ms_per_call` together with a higher moving-game
baseline; a lower present time by itself cannot manufacture 30 FPS when the
translated game worker remains CPU-bound.

## Hardware test

1. Finish the match and close the NRO with **HOME -> X -> Close**.
2. Extract one archive to the SD root and overwrite the existing files.
3. Keep the same forwarder, 1280x720 settings, game teams, camera, and OC.
4. Let the first launch reach the menu; close/reopen if the known startup
   stall occurs. Do not mix attempts in one comparison.
5. Play until a goal, replay, corner, or throw-in occurs and continue at least
   60 seconds after it. Preserve `pes13-nx.log` and all four
   `pes13-nx.previous-*.log` files before launching again.

For `cache-ab`, leave the match running across at least one 30-second toggle.
The startup line identifies the mode as `alternating from 60 s, 30 s off/30 s
on`. Compare `host_present_ms_per_call` while cleaning is on and off.

The confirming lines are:

```text
[INIT] core balancing on/off (no-balance.txt)
[PERF23] secondary_balance=0 history=4 ...
```

Compare the ten-second `[PERF8]` FPS windows and whether the frame rate returns
after the event. A real improvement is a higher post-event baseline, not only a
brief throw-in window.
