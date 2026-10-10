# Kit10: identify the Exhibition/controller-page stall

The Kit9 device test now passes initial loading and reaches the game menu.
The user reports a freeze between Exhibition and controller settings, while
audio remains smooth and HOME still works. This is a different symptom from
the previous complete console hang. The supplied log ends at 98.259 seconds.

## Evidence

- `[HZDIR] v4 asset_scan=1` confirms the new path is enabled.
- At 19.693 s, enumeration has completed 20,329 requests, including 16,962 asset
  names; no query is active. Timestamp lookup has made one call with less than
  one millisecond accumulated. The prior tens-of-seconds timestamp bottleneck
  is no longer present in this run.
- At 12.530 s, `kitserver13/plugin/gameplay.dll` fails process attachment with
  `c0000005`. Its preceding exception is a read at address zero. The process
  continues, presents frames, and later reaches the menu. This is a confirmed
  plugin initialization failure, but its relationship to the later stall is
  not established.
- The latest ordinary allocations complete successfully around 82.132 s.
  JIT statistics continue through 96.694 s, with almost no new compiled blocks
  after 86.676 s. There is no terminal guest exit or unhandled fatal record.
- High-address faults ending in `0xff0` also occur earlier while frames keep
  advancing. The existing VM observer documents the recoverable FEX prediction
  stack guard. The final such line alone is not evidence of the stall cause.

## Change and interpretation

Kit10 preserves the Kit9 asset scan and the exact Kit6 FEX module. It adds an
observer enabled only by Debug launch. The ordinary launch path does not
record diagnostic events or write diagnostic files.

The observer records entry and return at the native NT dispatcher, Wine server
round trips, and 17 Vulkan operation types. It never changes API arguments or
return values, dereferences guest argument pointers, suspends threads, walks
foreign stacks, starts a new worker, or performs SD I/O on a producer thread.
The existing maintenance worker reports every five seconds through the existing
bounded `fex-runtime.log` queue:

- `WAIT-PROBE`: frame count/progress, active calls, observation pressure.
- `WAIT-INFLIGHT`: entries with no recorded return for at least one second.
- `WAIT-CPU`: main thread and up to seven busiest registered threads, from
  kernel CPU counters; a busy registry is skipped with a try-lock.

The fixed 128-slot recorder uses generation-checked completion tokens. It drops
observations instead of blocking if full. Snapshot reads do not spin. Known
non-returning context/exception syscalls are excluded. Other exceptional
unwinds can still leave an entry without a return, so **an inflight record is
evidence to correlate, not proof of a deadlock**. Displayed idle duration has
the five-second observation granularity. A fresh CPU row is marked invalid
until two samples with the same live handle are available.

Vulkan codes: 0 acquire, 1 present, 2 submit, 3 fence wait, 4 semaphore wait,
5 graphics pipeline, 6 compute pipeline, 7 allocate memory, 8 create image,
9 create buffer, 10 shader module, 11 device idle, 12 queue idle.
NT and server IDs are bound to the packaged generated source.

## Controlled plugin comparison

The optional control changes only `kitserver13/plugin.ini` from the inspected
two-plugin configuration to camera-only. It omits the failing gameplay plugin
without modifying or redistributing any game/plugin DLL. This may change custom
gameplay behavior and is an isolation test, not a claimed emulator fix.
Back up the actual Switch `plugin.ini` before applying it, especially if it has
additional plugins. Restore that backup after the comparison.

First reproduce once on Kit10 with the current plugin list. If HOME still
responds, leave the freeze for about 15 seconds to collect multiple snapshots,
then close normally and retain the log. The optional comparison uses the same
NRO, preset, renderer and clocks, changing only that plugin list.

## Local validation and remaining work

The recorder is exercised under ASan/UBSan with 240,000 concurrent calls and
snapshots, capacity exhaustion, nesting, stale completions and error statuses.
The linked ARM64 checks execute the 8/16-argument NT dispatcher, quiet/debug
paths, bounded reporting and registered CPU counter path. Existing production,
startup, input, memory and asset-scan checks are required before packaging.

No Kit10 Switch test has been performed here. This build is intended to locate
the remaining wait and isolate the plugin failure; it does not claim to fix
the Exhibition freeze or increase gameplay FPS.
