# FEX3 final 3D attempt

This is the last FEX candidate requested by the tester before deciding whether
to return to Box64. It changes the runtime and compiler, beyond the already
tested Fast/Fastest settings. It has **not** been tested on a Switch and does
not establish 30 FPS, stock-clock performance, or successful kickoff.

## Evidence

Input: `fex-runtime.log`, SHA-256
`5307deca41759850e44cd5705e5b854e7da2e2ece561af78a6b68d6e5384196c`.
The log confirms ABI 3, native private heap, and **Fastest**: x87 64-bit,
scalar/vector/memcpy TSO off. Changing the same preset again is not a fix.

The native-heap change helped memory: this run has no terminal DXVK allocation
failure or access-violation exit, and the last progress report still has
616 MiB free native heap. Its 5-second BOOT counters advance from 1,759 presents
at 80 seconds to 2,025 at 120 seconds: **6.65 presents/s**. An earlier 50–55-second
interval reaches 60.2 presents/s. These are host presents, not unique game
simulation frames; scene boundaries and GPU execution time are not recorded.

The slow intervals report roughly 1.5–1.6 CPU cores in use. Each 10-second
server sample contains about 9,000–12,300 suspend calls, with matching handle
duplication/query/close traffic. The FEX adapter had added a 1 ms delay whenever
a local suspend returned `STATUS_NOT_SUPPORTED`. The log does not record the
status of every call, but the adapter's behavior is reproduced in the actual
old ARM64 ntdll test. Summed server wait times are overlapping wall times,
not CPU time and not a per-frame budget.

After the 120-second report, 128/64/32/16 MiB JIT allocations fail to find RW
alias space. FEX falls back to repeated 8 MiB generations. This is a separate
capacity/fragmentation problem; it cannot explain all earlier low cadence.

## Changes

1. **Remove the injected suspend delay.** Return the real callback status and
   count immediately, matching the working local Wine/Box64 bridge's
   `dlls/winebox64/cpu.c::BTCpuSuspendLocalThread`. There is no fake successful
   suspension. Horizon still cannot suspend an already-running thread. A game
   retry loop can therefore consume more CPU; on-device pacing remains to be
   measured. This change is in ARM64 **ntdll.dll**, so copying only the NRO
   or FEX DLL will miss it.

2. **Retire stale writable-code intervals on an explicit RX protection
   notification.** The pinned tracker inserted RWX intervals but retained them
   when an application restored executable/read-only protection. Our Horizon
   fallback consequently continued to emit per-instruction SMC checks. The
   real old/new ARM64 tracker test reproduces and fixes this for full and
   partial ranges, preserving invalidation and neighboring writable pages.
   Internal MTRACK trap operations use native NtProtectVirtualMemory and are
   distinct from these guest protection notifications.

3. **Batch remaining static-text checks at basic-block entry.** For Fast or
   Fastest, only successfully decoded blocks wholly inside the PE32 read-only
   executable `.text` of `pes2013.exe` or `d3d9.dll` qualify. Every byte still
   participates in a CRC check on every entry, including internal multiblock
   branch targets. A mismatch exits to the existing invalidation path before
   executing that block. Large blocks use exact-length chunks of at most
   255 bytes. Dynamic code, writable PE sections, unknown images, `rld.dll`,
   forced full-SMC blocks and disk-cache patching keep the instruction-level
   path. No game EXE bytes are patched.

   This borrows the block-validation approach visible in
   [Box64's dynablock implementation](https://github.com/ptitSeb/box64/blob/main/src/dynarec/dynablock.c),
   rather than disabling SMC globally. The FEX lowering is based on the
   [pinned FEX compiler](https://github.com/FEX-Emu/FEX/blob/e2f973fe931e6dc2ce523795e51ca1ac3ca85816/FEXCore/Source/Interface/Core/Core.cpp).
   This is an aggressive compatibility tradeoff: a qualifying `.text` block
   that modifies a later instruction **inside the same block** without a
   protection/flush notification is not checked again until its next entry.
   Ordinary dynamically generated guest code is excluded. This policy is not
   offered as a general-purpose replacement for FEX's full SMC mode.

4. **Reserve one extra 128 MiB JIT generation early.** The first cache remains
   128 MiB. An optional second mapping is acquired before DXVK fragments the
   address space, then consumed by normal cache rollover. No worker's live
   code is overwritten or reclaimed early. Reserve failure is nonfatal and
   keeps the normal allocation fallback. Cost: up to 128 MiB additional
   physical memory and two additional 128 MiB aliases, retained until used or
   the application exits. This protects one rollover, not unlimited growth.

Native private heap, exception recovery, x18 preservation, controller/save
paths and the graphics backend are retained. The archive selects Fastest
(`fex_fast=1`, `fex_fastest=1`), with production logging and no CPU sampler.
Fastest still relaxes scalar memory ordering and is experimental.

## Local validation

The delivered ARM64 binaries are checked with Unicorn and bounded NT/host
models, including:

- Old/new ntdll: rejected, invalid-handle, successful and null-count calls;
  old injected delay reproduced, new delay absent, status/count/TEB preserved.
- Old/new protection tracker: partial RX restore, neighboring RWX retention,
  re-enable write, whole-range RX restore, and four retained invalidations.
- 26 static-image policy cases and 1,214 code-byte mutations across CRC lengths
  1–255, including reads ending exactly at an unmapped page boundary.
- Early cache: retain a live old generation while consuming the 128 MiB spare
  with later allocations limited to 8 MiB; zero new mapping calls for that
  rollover; normal cleanup and nonfatal reserve failure.
- Existing callback ABI, alias ownership, code-growth, heap/profile and
  dynamic SMC regression tests.

For an artificial 128-byte sequence, the CRC emitter bodies total 192 ARM
instructions for 32 four-byte checks versus 42 for first-instruction plus
remainder checks. This excludes expected-value loads, address setup, the OR,
failure edges and guest instructions; it is **not a game speedup measurement**.
`[FEX3-SMC2]` provides bounded compilation counts to determine whether the
policy actually applies on the Switch. Counts are not execution samples.

## Install

Close the app via HOME → X. Extract `pes13-fex3-final-3d.zip` at the SD root,
overwriting the complete `switch` folder contents from this package. It has
one NRO and updates four runtime files:

```text
switch/pes13-fex/
  pes13-fex.nro
  configuration.ini
  drive_c/windows/system32/
    libwow64fex.dll
    ntdll.dll
```

It launches PES directly (`run_guest_tests=0`). Keep the same forwarder,
game data, saves, settings, resolution and clocks for the comparison. First
check whether team selection becomes responsive and kickoff is reached, then
play through a replay/corner. Preserve `switch/pes13-fex/fex-runtime.log`.

Expected markers: `[BUILD] pes13-fex3-final-3d`, `[FEX3-SUSPEND]`,
`[FEX3-SMC] v2`, and either `early spare ready` or `early spare unavailable`.
The separate `pes13-fex3-final-3d-rollback.zip` restores the exact prior
Fastest-native NRO/FEX/ntdll/config combination; it is **not a Box64 rollback**.
If this final attempt still cannot reach playable kickoff, continue work on
the established Box64 backend instead of extending this FEX test series.
