# FEX3 sync regression recovery

The tester reports CPU-only OC, heavier 3D and a complete freeze **before
kick-off** with `pes13-fex3-sync-pacing`. This is a failed device candidate.
Do not use its present counts as an in-match FPS benchmark.

## Evidence

Input: `local/fex3/sync-result/fex-runtime.log`, 119,184 bytes, SHA-256
`7f2f30bf7e21e630550463cb58126bc573fb7b776cfdcd4659eb649e8de54f80`.
Reproduce `analysis.json` with `tools/analyze-fex-sync-regression.py`, using
the archived **sync-pacing** ELF, not the recovery ELF, to symbolize addresses.

- The final report has no new presents for 29,658 ms; there is no `[EXC]` crash
  report. This is evidence of a stopped rendering stream, corroborated by the
  tester's complete freeze.
- The router filtered 1,188,692 of 1,426,806 candidate notifications (83.31%).
  Fewer notification attempts did not establish a performance benefit.
- Sleep/yield observations show up to 1,185,473 us of excess sleep wall time.
  Multiple game workers incur long overshoots, while the shared clock update
  has a recorded maximum gap of only 7,698 us. Overshoot includes scheduling,
  preemption and contention; this does not measure GPU execution.
- Linked-ELF symbolization places threads 4 and 24 in `svcWaitForAddress` via
  `horizon_futex_wait` / `NtWaitForAlertByThreadId`. Thread 96 repeats guest
  atomics and also appears in `NtYieldExecution`; thread 92 waits for a server
  reply through `NtWaitForSingleObject`. Guest block labels are not exact PCs
  or verified module names.
- The last self-suspend report has 9,225 requests and 9,225 returns, with none
  outstanding at that sample. This is not a full live dependency graph.

The evidence warrants withdrawing the new wakeup default. It does not prove
the exact deadlock cycle or whether changed scheduling exposed an older race.
The previous run and this run also have different scene timelines; a claimed
percentage FPS loss or gain would be unjustified.

## Change

Build `pes13-fex3-sync-recovery` defaults `fex_targeted_wake` to **0** in both
the runtime and packaged INI. Shared wakeups use the original condition and
wait function. Mode 0 bypasses wire-interest decoding, router registration,
per-object handle lookups, list walking and routing counters. The earlier
control switch still did some router work; this build removes that cost.

The opt-in routing code remains available for development but is not enabled
in this package. Original status/timeout handling and synchronous self-suspend
are preserved. FEX DLL/Fastest settings, ntdll DLL, DXVK DLL/configuration,
guest clocks and game/save data remain the same. Passive Sleep/yield and
pipeline counters remain so the next run can be compared; no hot-path I/O
or new timing/priority policy is introduced.

This is a regression recovery, not a new 30 FPS claim or a hardware-verified
fix for the original pause/fast-motion symptom.

## Install and validate

After HOME -> X -> Close, copy `dist/pes13-fex3-sync-recovery/switch` to the
SD root and overwrite all five supplied files, including `configuration.ini`.
Use the same `switch/pes13-fex/pes13-fex.nro` forwarder. Do not delete saves or
game files. There is no ZIP. Earlier artifacts are preserved for comparison.

The log must show `[BUILD] pes13-fex3-sync-recovery` and
`[FEX3-SYNC] startup targeted=0`. Routing counters stay zero in this mode
because that code is bypassed; this is expected, not a stopped server.

Keep clock settings fixed from launch. First check that team selection and
kick-off work again. If successful, play several minutes with quick passes
and a replay, then preserve `fex-runtime.log` before restarting. Do not enable
targeted wakeups during this recovery test.

Local checks cover unchanged wait/status/clock policy, ASan/UBSan stress,
18,000 adapter handoffs including shared gates and control mode, zero router
work in control mode, actual linked ARM64 routing/self-suspend, FEX ABI/heap
and packaging hashes. They do not reproduce Horizon's scheduler or prove
on-device performance. Build through WSL; package using
`python tools/package-fex3-sync-pacing.py --recovery`.
