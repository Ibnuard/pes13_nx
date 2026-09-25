# FEX3: native private heap and Fast / Fastest profiles

This is an experimental FEX candidate. Box64 remains the working PES backend;
no Switch gameplay/FPS result exists yet for this build.

## What the latest device log establishes

The user reports that both alias-perf control and same-core Sleep(0) still hang
at team selection. The supplied log has no same-core marker. Its SHA-256 is
`b5ae514af2503d2f597077e21bac6eda7196e2e9566443c1845b8417ac5b833c`.
It contains repeated failed **16,448 KiB guest-VA reservations**, followed by
failed Vulkan allocations from 128 down to 16 MiB. DXVK then reports a memory
allocation failure and the main thread exits with `c0000005` on address `0x6c`.
That is an allocation failure followed by a crash, not evidence that the GPU
is merely rendering a difficult scene. Free native heap falls from 353 MiB
at the 85-second progress sample to 86 MiB at 105 seconds. Audio underruns
and low present deltas already appear before the final crash.

At the first VA failure Wine reports 1,017 MiB of anonymous views, 642 MiB
committed, plus a 2 GiB native system view. Not all anonymous memory belongs
to FEX. The native physical backing and guest aliases compete for the same
low 4 GiB address space. A kernel-free hole is not necessarily Wine-allocatable.

The first 24 HMAP diagnostics are consumed by startup probes which recover;
they do not identify a new failing heap-commit operation in this log. The
previous control's `c0000022` commit failure therefore remains a separate
unverified failure case.

## Changes

FEX's private CRT and C++ container allocations now use the native allocator,
including malloc/free, calloc, realloc, aligned allocation and usable-size.
They no longer reserve rpmalloc spans through Wine or create guest aliases
for their backing. Thread teardown does not create or retain per-thread
rpmalloc spans. Guest VirtualAlloc, guard pages, guest CRTs, SMC tracking,
code-cache capacity and JIT CodeMemory mappings retain their existing paths.
The native/PE host interface is version 3, so install the NRO and DLL together.

This aims to reduce low-address-space pressure and VM/kernel work during
compilation and container growth. Native malloc has different locking and
allocation costs from rpmalloc; an FPS gain must be measured on Switch.
`[FEX3-NHEAP]` reports live/peak requested bytes and failures at the existing
progress cadence. It does not log each allocation. Those counters exclude
allocator overhead, separate scratch allocations, JIT code and game memory.

The names **Fast** and **Fastest** are project profiles, not a universal
upstream FEX preset. Their values use actual options in the pinned FEX source:

| Option | Previous/default control | Fast | Fastest |
|---|---:|---:|---:|
| X87ReducedPrecision | false (80-bit) | true (64-bit) | true (64-bit) |
| TSOEnabled | true | true | false |
| VectorTSOEnabled | false | false | false |
| MemcpySetTSOEnabled | false | false | false |
| HalfBarrierTSOEnabled | true | true | true |
| Multiblock / MaxInst | true / 5000 | true / 5000 | true / 5000 |
| SMCChecks | mtrack | mtrack | mtrack |

Fast targets software x87 arithmetic overhead. Fastest additionally relaxes
ordinary scalar memory ordering and can cause multithreaded game/renderer
errors; use it as the aggressive comparison. LOCK instructions are retained.
Neither profile enables ARM instructions unsupported by Cortex-A57. Vector
and memcpy TSO were already off and are not claimed as new optimizations.
The ineffective same-core Sleep(0) experiment is not enabled.

Primary references: [pinned FEX options](https://github.com/FEX-Emu/FEX/blob/e2f973fe931e6dc2ce523795e51ca1ac3ca85816/FEXCore/Source/Interface/Config/Config.json.in),
[upstream explanation of TSO costs](https://fex-emu.com/FEX-2406/).

## Install and compare

1. Close PES via HOME → X. Extract `pes13-fex3-fast-native.zip` at the microSD
   root, overwriting the NRO, DLL and configuration.ini in `switch/pes13-fex`.
   The existing forwarder path stays `switch/pes13-fex/pes13-fex.nro`.
2. This package sets `run_guest_tests=0`, `fex_fast=1`, `fex_fastest=0`.
   The log must show `[FEX-HOST] ABI 3`, `[FEX3-HEAP] v8`, and
   `[FEX3-PRESET] fast x87=64 scalar_tso=1`.
3. Compare menu, team selection and the same kickoff scene at unchanged clocks
   and graphics. Preserve `fex-runtime.log` before the next launch. Note time
   to team selection, responsiveness, audio and whether a match is reached.
4. For the second profile, change **only** `fex_fastest=1` in configuration.ini,
   or install `pes13-fex3-fastest-native.zip`. Its NRO and DLL are identical.
   Its marker is `[FEX3-PRESET] fastest x87=64 scalar_tso=0`.
   Return to `fex_fastest=0` to restore Fast. No shader-cache or save deletion.

`fex_fast=0` and `fex_fastest=0` select control arithmetic/order settings with
the new heap. `run_guest_tests=1` always selects those control settings for
the existing stress workload. `pes13-fex3-fast-native-rollback.zip` restores
the previous alias-perf control NRO/DLL; old builds ignore the new INI keys.
These packages contain no game assets, saves or replacement graphics settings.

## Verification and limits

Both ARM64 builds succeed. Linked-code tests cover native size/alignment,
failed allocations, ownership/counters, CRT grow/shrink/failed realloc,
calloc overflow, cross-worker frees, preservation of the Wine x18 register,
real FEX config setters/getters, cache alias lookup, lookup-memory management
and 17 code-cache growth/lifetime scenarios. The heap model exercises 32
worker identities and 96 live CRT blocks without any guest VM request.
Native host tests also run concurrent allocation and cross-thread frees under
ASan/UBSan. These tests do not emulate Horizon scheduling or run PES.

On-device hang resolution, audio stability, visual correctness, and performance
are still unverified. No claim of reaching or maintaining 30 FPS is made.
