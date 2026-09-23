# PERF8: mutex repair and measured block policy

Hardware testing is pending. Use CPU 1728 / GPU 768 / RAM 1600 MHz for both
runs. The PERF7 log lacked the profile activation marker, and supplied no
periodic match measurements. Earlier 19 FPS figures mixed menus and gameplay;
they are not a controlled match benchmark.

PERF8 fixes an error in PERF6/7's counter removal: removing only the body of
an `if (mutex == &core_context.mutex_dyndump)` made the following real mutex
lock conditional. Other mutexes could be skipped and `ret` read uninitialized.
PERF8 removes the entire diagnostic conditional, preserving unconditional
locking. Its impact on hardware has not yet been measured.

The profile is now selected directly by Box64's `GetCurEnvByAddr`, called
inside block compilation under the translator mutex. After the first successful
Vulkan present (SUCCESS or SUBOPTIMAL with a swapchain), new translation
attempts use an immutable per-block `BIGBLOCK=1` override. Global environment,
existing compiled blocks, SAFEFLAGS, FASTNAN, FASTROUND, STRONGMEM, X87DOUBLE
and CALLRET remain Compatible. This deliberately narrows the failed PERF7
experiment: the pinned translator supports a per-block BIGBLOCK override,
whereas many other controls read shared global state. This is not a promise
that later game execution cannot regress.

Install: close PES through HOME, extract `switch` to SD root and overwrite.
Use the same forwarder. No game binaries, saves, or settings.dat are included.
`ntdll.dll` and the startup Box64 profile remain byte-identical to PERF3.

Expected markers:

- `pes13-nx-0.2.0-perf8-block-profile`
- `[BOX64] PERF8 block profile armed`
- `[BOX64] PERF8 block profile active` on the first new block after a present
- `[PERF8]` and `[THREADS]` about every 10 seconds

Metrics are interval values: successful presents, FPS, average time per present,
host vkQueuePresentKHR wall time per call, active policy and translation attempts.
The latter counts attempted compilations, not executed or successfully compiled
blocks. Host present time includes waits and is NOT GPU render time. A zero
present count means average frame duration is unavailable (printed as 0).
No per-draw or per-instruction logging is enabled. Thread reports cover registered
Wine/server threads; they are not a complete GPU or system utilization measure.

Test the same teams, stadium and camera for at least 60 seconds of match play.
Then change `switch/pes13-nx/perf8-turbo.txt` from `1` to `0`, restart, and repeat
at the same clocks. This disables only the block override, retaining the mutex
fix and telemetry for a controlled comparison. Save each log separately.
If profile-on regresses, use `0`; if both regress, the previous PERF6 overlay is
available as a diagnostic rollback, but contains the mutex-removal bug above.

Build without Docker:

```
PES_BUILD_ROOT=/home/blekjek/pes13-build python3 tools/build-perf8-test.py
```
