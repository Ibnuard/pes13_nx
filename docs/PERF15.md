# PERF15 — deliver guest exceptions to WoW64

This test targets the latest startup failure. It is not a measured FPS
optimization and has not yet been tested on Switch hardware.

## Evidence

The supplied PERF14 log ends game execution with `STATUS_ACCESS_VIOLATION`
(`0xc0000005`), reading address `0x4`. The native fault maps to guest PC
`0x0115c36f`, but the engine returns the stale saved EIP `0xff6bd55c` and
BTCpuSimulate immediately terminates the process. Subsequent intervals have
zero presents. The loading spinner is the last displayed frame.

This log has no mapping-failure report or `bad_alloc` like the previous
startup failure. It does not establish why alternate launches work, or
whether PES has a handler that can recover from this particular access.

Archived log: `local/perf15/perf14-first-launch-access-violation.log`, SHA256
`fef9f95cca8b5c0fa6afe08b3adacf2109d9ffac295ff4afc9766a0241c46221`.

## Change

Backport the 32-bit guest-exception parts of upstream
[e04029a51e](https://github.com/danfromtico/autorun/commit/e04029a51e)
and the related callback return-value correction from
[8f3e5f78f5](https://github.com/danfromtico/autorun/commit/8f3e5f78f5).
The checked patches are stored in `patches/perf15/`.

- Recover x86 general registers, flags and instruction address from the ARM64
  fault snapshot when the PC maps to translated guest code. Undo upstream's
  supported partial POP/MOVS register effects.
- Carry the fault address and read/write/execute kind across native ABI 4.
- Raise access violations, integer division-by-zero, breakpoints and illegal
  instructions through the installed wow64.dll's `Wow64RaiseException`,
  giving the application's handlers the opportunity to respond.
- Preserve the call's return value when a native callback replaced the x86
  context. NtContinue already returns the restored context's EAX.
- On a fault during compilation, jump to Box64 0.4.4's active FillBlock
  recovery boundary. Its own cleanup owns CancelBlock64; calling it before
  the jump would invalidate the helper. No guest success is fabricated.
- Enable Box64's integer divide-by-zero check, matching the interpreter.

The Compatible math/memory/call settings, Box64 0.4.4 `-O1`, PERF14 mapping
guards, installed PERF13 suspend-backoff ntdll, DXVK and controller/save
settings are retained. Profiling and turbo remain off. Fault summaries in
the Unix bridge and native register dumps are each capped at 16; exception
dispatch continues after the diagnostic cap. There is no new per-frame trace.

This does not implement universal native signal recovery or restore every
possible partially executed SIMD/x87 instruction. Unhandled game exceptions
can still terminate the game. The actual Switch run is needed to establish
whether this fixes the startup symptom.

## Install and compare

1. Close PES completely via HOME → X → Close.
2. Extract **pes13-perf15-guest-exceptions.zip** at the SD root, overwriting
   the `switch` folder. Copy both the NRO and the included ARM64
   `drive_c/windows/system32/winebox64.dll`; ABI 4 requires this matched pair.
3. Use the same forwarder: `switch/pes13-nx/pes13-nx.nro`. No save, cache or
   game-data deletion is needed. The log build marker should be
   `pes13-nx-0.2.0-perf15-guest-exceptions`.
4. Try three launches without rebooting, fully closing between attempts.
   Preserve `switch/pes13-nx/pes13-nx.log` after each attempt before it is
   overwritten. If startup works, check the same team screen and match with
   the same clocks/settings.

**pes13-perf15-rollback.zip** restores the exact PERF14 NRO and previous ABI 3
winebox64.dll. Always restore both together; PERF14's older NRO-only rollback
does not undo the DLL change in this experiment.

## Validation and reproduction

Run in WSL (no Docker):

```sh
PES_BUILD_ROOT=/home/blekjek/pes13-build python3 tools/build-perf15.py
```

The builder runs host probes of the actual patched recovery/exception-record
helpers, including translated PC rejection, register recovery, partial
POP/MOVS, and the active compiler fallback. It also runs the shared gate and
native ABI tests, including old-version/size rejection, callback return
values, fault metadata, quiet logging and bounded diagnostics. These are
host tests; they do not execute ARM64 translated game code.

The runtime build reruns PERF8 policy/locking, PERF10 wakeup and PERF14
mapping tests. Source snapshots are restored in `finally`, including PE
inputs and the original winebox64 build outputs. Packaging validates NRO
assets, PE architecture/import availability, both payload hashes and ZIP
integrity. No game EXE, save or proprietary DLL is included in the package.
