# FEX3 team-selection synchronization candidate

The tester reports that `final-3d` has brought the 2D path close to Box64, but
team selection stops progressing. This candidate retains those optimizations
and tests memory ordering as one specific cause. **It has not been validated
on the Switch, and is not a confirmed fix or FPS improvement.**

## New evidence

Input SHA-256: `ef2b2cac42b684afaf465227e505dc53db159c5d1a328c58e1e1de24f4685c5e`.

- Build is `pes13-fex3-final-3d`, ABI 3, Fastest; all three TSO options are off.
- Presents rise from 752 at 40 seconds to 1,054 at 45 seconds: 60.4 host
  presents/s in that interval. This is not a unique simulation-frame count.
- Presents stop at 2,036 from 65 through 85 seconds. Reads and private-heap
  allocation counts also stop. There is no terminal exception or allocation
  failure at the stall; the reported native heap still has 644 MiB free.
- The last ten-second server window has 510,050 suspend requests and roughly
  matching duplicate/query/close counts. Main tid 4 and game workers 72/124
  remain busy. The old log does not identify each suspend target or result.
- The early spare JIT mapping succeeds. No cache rollover failure appears at
  the stall. The recorded SMC entry-guard count is zero: the scope-limited
  batching path does not explain this run's improvement.

The evidence supports investigating a CPU/thread progress failure. It does
not prove a particular lock, memory-ordering bug, or shader-driver defect.

## Changes

The installed configuration selects **Fast**, with x87 at 64-bit precision
and scalar, vector and memcpy/string TSO all enabled. The older Fast profile
enabled only scalar TSO. Fastest still exists as an explicit diagnostic
override, but is not selected by this package. Disabling memory ordering is
not a generally valid substitute for x86 synchronization on ARM64. Restoring
ordering can cost CPU time; the hardware run must establish the tradeoff.

The RX interval fix, native private heap, bounded static-text checks, early
128 MiB spare cache and zero injected suspend delay remain. The new DLL also
checks the pinned FEX CPU-state and JIT-tail layouts used by the observer at
compile time. The host ABI remains 3. The shipped ntdll is byte-identical to
`final-3d`; it is included to keep the update self-contained.

Two bounded observations provide actionable evidence if this change is not
sufficient:

1. `[FEX3-SUSPEND-RESULT]` aggregates real caller/target/status counts at the
   existing progress-report cadence. It adds no per-call SD I/O and does not
   invent successful suspension, add sleeps or change suspend counts.
2. After at least 100 presents and ten seconds with no progress,
   `[FEX3-HANG*]` briefly pauses the main thread and up to three busy Wine
   threads using the existing profiler's Horizon APIs. Each successful pause
   is followed by a resume, including context-read failures. Two observations
   are taken two milliseconds apart, with a maximum of three capture bursts
   per process. Normal continuous profiling stays off. Logging happens only
   after all observed threads have resumed.

Snapshots report native PC/registers, bounded native callers, and—when the
PC is in a registered FEX JIT mapping—the current block label and last stored
guest RIP. These are **not exact guest-PC samples**. The observer's native
address plus the archived ELF makes native PCs resolvable despite ASLR.
An unavailable pause/context permission is logged without issuing the
unavailable operation. A legitimate long load can also trigger this observer.

## Validation

- WSL builds the ARM64 FEX DLL and native NRO successfully.
- The actual DLL's typed configuration getters confirm scalar, vector and
  memcpy TSO for Fast, and keep x87 at 64-bit precision.
- Linked ARM64 ABI, alias, heap/profile, code-growth and existing SMC/cache
  tests pass. These use bounded API models, not a Switch.
- The actual observer C code passes ASan/UBSan tests for moving-frame
  suppression, the capture limit, pause/context errors, resume retry,
  missing permissions, thread unregister and read-range rejection.
- One million modeled suspend observations produce no per-call log output;
  reporting preserves actual results and emits only changed counters.

## Install and test

Close via HOME → X. Copy the ZIP's entire `switch` folder to the SD root and
overwrite its four files:

```text
switch/pes13-fex/pes13-fex.nro
switch/pes13-fex/configuration.ini
switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll
switch/pes13-fex/drive_c/windows/system32/ntdll.dll
```

Keep the forwarder and game/save data. The INI already selects PES directly,
Fast, production logging, and `profile=0`. Keep clocks/resolution the same as
the last run. The log must say `pes13-fex3-team-sync` and
`fast x87=64 scalar_tso=1 vector_tso=1 memcpy_tso=1`.

Try Exhibition → controller → team selection → kickoff. If it freezes,
wait **20–30 seconds** before HOME → X so the bounded snapshots finish, then
preserve `switch/pes13-fex/fex-runtime.log`. No verbose/profile TXT is needed.
The separate rollback restores the exact `final-3d` four-file combination.
It restores FEX, not Box64.
