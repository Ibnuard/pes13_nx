# PERF13 — backoff after unsupported running-thread suspension

Experimental A/B test on top of PERF12. Expected installation: PERF11 NRO
(Box64 0.4.4), fixed Compatible preset, DXVK unchanged, PERF12 ARM64 ntdll.
The NRO banner continues to say PERF11; this package replaces only the native
ntdll and reasserts the same profiling-off / Compatible configuration.

## Change

`RtlWow64SuspendThread` still calls `NtSuspendThread` for every request.
Only when it returns `STATUS_NOT_SUPPORTED` does the caller execute a
non-alertable relative `NtDelayExecution` of 1 ms. The original status is
returned and the output count remains governed by the native call. Successful
start-gate suspension, nesting, invalid handles, terminated-thread errors and
suspend-limit errors are unchanged. No return-value cache is used.

The delay happens after the server request returns and after its object mutex
has been released. Game-held locks may still be held by the caller; this is
why the change needs a hardware A/B test. A requested 1 ms sleep can last
longer under contention. It does not implement running-thread suspension or
guarantee improved performance, stable boot, or 30 FPS.

## Install and test

1. Close PES through HOME -> X -> Close.
2. Extract **pes13-perf13-suspend-backoff.zip** into the SD root, overwriting
   its `switch` folder. No new forwarder is needed.
3. Keep the same clocks and settings. Check that the previously smooth 2D
   screens remain smooth. Enter the same team selection screen with the two
   player models and leave it there for about 45–60 seconds. Try a match if
   responsiveness allows.
4. Close and save `switch/pes13-nx/pes13-nx.log` before opening PES again.
   Report whether this was the first boot or a reopened run, whether 2D
   regressed, and whether models/menus improved. The low-rate `[SERVER]`,
   `[THREADS]` and `[PERF8]` statistics are sufficient for the initial test;
   keep the sampling profiler off for FPS comparison.

If startup, input or animation regresses, install
**pes13-perf13-rollback-perf12.zip** in the same way. Its ARM64 ntdll is a
byte-identical copy of the PERF12 test DLL, SHA256
`613a22358e6cdca18bb6bb1fc8522b5d79cf08e485e309997c2533b04ffca855`.
This rollback is not the old PERF3 fake-success fallback.

Both ZIPs leave the NRO, Box64 preset file, DXVK, x86 ntdll, game files,
controller configuration, settings.dat and saves unchanged. They set
`profile.txt=0`, `perf8-turbo.txt=0`, and the same per-game settings as PERF12.

## Validation scope

The host contract test compiles the shipped wrapper with the actual Horizon
server suspend handler and thread-state helper. It exercises successful and
nested suspensions, invalid/access-denied handles, terminated threads, the
suspend limit, repeated refusal, a reused handle and unchanged output on
errors. The delay stub verifies that the server mutex is released and that
only the intended error requests a non-alertable 1 ms sleep. These are
contract tests, not Switch scheduler or game tests.

Packaging checks ARM64 architecture, identical PE exports/imports, linked
calls to native `NtSuspendThread` and `NtDelayExecution`, ZIP contents/CRC,
hashes and byte-identical PERF12 rollback. The build restores the original
source, object and DLL even if it fails.

