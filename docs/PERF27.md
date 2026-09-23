# PERF27 — targeted Wine-NX synchronization

This is an experimental Wine-NX change, not another Box64 preset. A Switch
performance improvement and a fix for slowdown after events are **not yet
established**. A sustained 30 FPS is still a target.

## Install

Close the game with HOME → X → Close. Extract `pes13-perf27-wakes.zip` to the
SD root and overwrite. Launch the existing forwarder: there is still one
`switch/pes13-nx/pes13-nx.nro`. The build marker is
`pes13-nx-0.2.0-perf27-wakes`, and `[SYNC27] targeted=1` confirms activation.

Keep CPU 1728 / GPU 768 / RAM 1600, 1280×720, and the same teams, stadium and
camera. Play five real minutes, including a lofted ball, replay and foul/goal,
then ordinary play for 30–60 seconds. Note elapsed real time from launch when
the slowdown begins. Save the current log and four previous logs before more
launches rotate them.

`pes13-perf27-control.zip` switches only `perf27-targeted-wake.txt` to 0 on the
same NRO. Close and relaunch for a matched comparison. It uses the original
shared-condition broadcast path, with the same timing and notification
counters. Reapply the main package to turn targeted routing back on.
`pes13-perf27-rollback.zip` restores the exact PERF26 NRO and configuration.
Game executables, saves, settings.dat and controller mapping are untouched.

## Why this target

PERF26 measured about 16.3 presents/s during the long match candidate. After a
worker transition, cadence fell to about 14.6 and host-present wall time rose
from about 1.0 to 7.8 ms. Worker replacement, a foul and presentation waits are
not proven causal links. Prior sampling also found much translated game code,
so fixing server overhead alone may leave the main CPU limit intact.

The Horizon server normally broadcasts every relevant object change to all
sleeping selects. Frequent event/mutex traffic can wake unrelated clients,
which contend for the shared object lock and then sleep again. PERF27 records
each waiting select's handles and routes event, semaphore and mutex changes
only to waiters referring to that object. It resolves handle aliases under
the object lock; invalid handles trigger a recheck instead of being ignored.

Thread startup, thread exit/mutex abandonment, completion ports, messages and
unknown operations retain broad notifications. Waits containing files, timers,
message queues or other unclassified objects also retain broad interests, so
their opportunistic rechecks are not lost. WAIT_ALL remains interested
in every listed object. No wakeup claims ownership or returns success: the
existing server still checks and consumes the signaled objects. The original
20 ms safety recheck, 1 ms message polling, timeout arithmetic, locks and
PERF10 resume-gate fix remain. Registration and removal happen under the same
mutex as state changes, with atomic condition wait/unlock.

CPU translation and its generated sources remain PERF26: SAFEFLAGS=2,
STRONGMEM=1, BIGBLOCK=0, FASTNAN=0, scoped FASTROUND=1/X87DOUBLE=1/CALLRET=2,
and startup CALLRET=0. Mesa, DXVK, the renderer and frame limit are unchanged.

## Diagnostics and validation

`[SYNC27]` reports notification candidates, attempts delivered/filtered and
sleep registrations per ten-second window. A notification attempt is not a
guaranteed OS wakeup or successful object acquisition. Control mode adds
accounting to the original broadcast path; rollback is the exact baseline.

`[PIPE27]` separates present total, its mutex wait, surface bookkeeping,
acquire, driver submission, fence/semaphore waits and idle waits. These are
CPU-side wall durations, including descheduling; they are **not GPU timers**.
Nested and concurrent spans must not be summed into a frame budget. Maxima
are since launch; interval boundaries are approximate. Host-present timing
continues in `[FRAME24]`. The CPU sampler stays off. No new per-call SD writes,
allocation or suspension of game threads is introduced by timing counters.

Host tests use the actual routing header: wire layouts with/without APC data,
aliases, closed/pseudo-handles, WAIT_ALL dependencies, broad fallback, timeout
cleanup and 16,000 concurrent handoffs without polling fallback. ASan/UBSan
checks memory/undefined behavior. A synthetic 20-waiter case filters 95% of
notification attempts; this is not an FPS benchmark. Tests also compare
unchanged server result/consumption functions, and verify linked ARM64 hooks,
restored build sources and unchanged CPU emitters. Linux pthread tests do not
validate Horizon scheduling behavior; Switch A/B testing remains necessary.

The native wait uses libnx's atomic wait/unlock and reacquire-on-timeout
contract; see the [libnx implementation](https://github.com/switchbrew/libnx/blob/master/nx/source/kernel/condvar.c).
The local pinned Wine-NX source and compiled artifact remain authoritative
for this build; this change does not import Linux fsync/esync or a new driver.

Build without Docker under WSL:

```
PES_BUILD_ROOT=/home/blekjek/pes13-build python3 tools/build-perf27.py
PES_BUILD_ROOT=/home/blekjek/pes13-build python3 tools/verify-perf27.py
python3 tools/package-perf27.py
```
