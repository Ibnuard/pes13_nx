# Kit16: reduce FEX decoder workspace demand

The latest Kit15 device run fails while loading toward kick-off. At 120–122
seconds, guest commits repeatedly fail; backing allocation reports `ENOMEM`.
At 122.142 seconds FEX then requests an 8 MiB compiler scratch buffer, receives
NULL and emits `STOP compiler scratch failed`. The following breakpoint is
unhandled and that thread is parked. The final Vulkan counters show all 32,392
calls returned. This is direct evidence of allocation failure, not a remaining
Vulkan call or ordinary slow Kitserver loading.

The failure report has about 38.8 MiB of aggregate free heap, no untaken heap,
and a fully occupied 64 MiB reserve. `pages_stage=4` means backing allocation
failed. Aggregate free bytes do not promise a usable aligned allocation. The
log does not identify the precise cause of every earlier commit failure.

## Change

The FEX frontend previously requested 65,536 decoded-instruction records on
every fresh pool allocation. At 128 bytes per record, that is 8 MiB. This run
uses a maximum of 128 instructions per compilation; the decoder already stops
at that limit. Kit16 requests only the effective limit, clamped to 1–65,536.

| Effective instruction limit | Old request | Kit16 request |
| --- | ---: | ---: |
| 128 | 8 MiB | 16 KiB |
| 500 | 8 MiB | 62.5 KiB |
| 5,000 | 8 MiB | 625 KiB |
| 65,536 or higher | 8 MiB | 8 MiB |

The instruction limit itself is unchanged. Buffer growth occurs only when a
new compilation starts, before decoded-block pointers are published. The
existing pool ownership/reuse logic is retained. An explicit release-build
bound protects the decode loop, including pause/resume and invalid paths.
The 16 MiB IR workspace, generated-code cache and optimizer remain unchanged.

This is a reduction in one workspace request, **not** a measurement of total
process memory saved. The host's early 64 MiB reserve still exists; its idle
pages remain available to the existing pressure-recovery allocator. Small
decoder buffers use ordinary page-aligned allocations first rather than
occupying an entire 8 MiB reserve unit. Other game/Kitserver allocations can
still exhaust memory. Kit15's transactional commit correction remains present.

## Build and validation

The module uses the exact Kit6 input that shipped with Kit7–15. Full source-tree
comparison permits only `Frontend.cpp`, `Frontend.h` and the startup log label
in `WOW64/Module.cpp` to differ. Adapter sources, profiles, compiler flags and
upstream pin are unchanged. The NRO is byte-for-byte Kit15, so the launcher still
displays `0.3.9-kit15`. The DLL identifies itself in Debug launch with:

`[FEX3-SCRATCH] v2 kit16 decoder capacity follows block limit; IR capacity and JIT limits unchanged`

Validation includes:

- 384 differential runs of the actual old/new DecodeLoop source under ASan and
  UBSan, with modeled instruction decoding. Decoded addresses, blocks and counts
  match for ordinary, branching, invalid, overlapping, and paused workloads.
- Actual ARM64 DLL setup/pool execution verifies default/explicit limits,
  concurrent owners, grow/reuse/free and bounds. With a modeled 3 MiB scratch
  budget, the old 8 MiB request stops; eight candidate decoders fit in 128 KiB.
- Actual Kit15 ARM64 host callbacks verify page rounding of the new sizes,
  no 8 MiB reserve unit consumed for small buffers, and unchanged 16 MiB IR
  allocation/release.
- Linked allocation, pool ownership, self-modifying-code guards, x87 state,
  physical timer, profile and import compatibility checks.

These tests model host/kernel boundaries. They do not run a complete PES match
or demonstrate a Switch FPS improvement or successful kick-off. Retest the
same Kitserver workload before treating the freeze as resolved.

## Installation and device test

Close PES. Copy the package's `switch/` directory to the SD root, replacing the
NRO and `drive_c/windows/system32/libwow64fex.dll`. Both are included so the
matching host/module pair is explicit; the NRO itself remains Kit15.

Keep the same Medium preset, renderer, clocks and patch. Use the existing
32-bit no-alias NSP and Debug launch, then Exhibition → game plan → kick-off.
Confirm the **Kit16 module marker** above; the launcher version alone cannot
identify this DLL. Return `fex-runtime.log`, including on success. If it freezes
and HOME responds, wait about 15 seconds before closing.

Normal Launch still writes no diagnostic logs. Saves and functional settings
remain enabled. Check runtime can mark this experimental DLL as changed;
Repair runtime replaces it, so copy the candidate back if Repair is used.
Rollback contains the exact Kit15 NRO and previous FEX DLL. No ZIP, game files
or Kitserver plugin binaries are included.
