# Kit17: DXVK storage under memory pressure

The Kit16 run reaches the prematch pitch but does not reach kick-off. Its log
confirms the Kit16 FEX module is installed. The earlier 8 MiB decoder scratch
failure is absent. At 139.641 seconds Vulkan allocations of 128, 64 and 32 MiB
begin failing; later entries include 16 and 8 MiB. There are 32 logged failures,
the diagnostic cap, so this is not a complete allocation history.

At 188.798 seconds the main thread has an unhandled read of `0x6c` at
`0xfe4efa4f`; at 188.928 it self-terminates with `0xc0000005` and parks. Another
thread reaches the same fault later. This run is an exception followed by the
runtime's parked exit path, not evidence of ordinary Kitserver loading.

The loaded D3D9 base is `0xfe360000`. RVA `0x18fa4f` in the exact shipped
DXVK DLL reads `[edx + 0x6c]` immediately after loading the storage pointer from
`[esi + 0xb0]`. This matches `DxvkImage::assignStorageWithUsage` in pinned DXVK
3.1.1: an image allocation can return NULL, but the constructor still reaches
`m_storage->getMemoryProperties()`. Function attribution is based on disassembly
and source correspondence; original release debug symbols are not available.

## Changes

The new D3D9 DLL is built from upstream 3.1.1 commit
`b1a1c99ab52b687cf950d62c88bc2fa316b41663`, with five source files changed:

- Ordinary pooled Vulkan allocation growth is capped at **8 MiB**, rather than
  growing to 128 MiB for small resources. Larger resources still request their
  full required size.
- A bounded retry loop reaches the exact 64 KiB-aligned resource floor. Upstream
  can stop at a larger pool floor or skip a non-power-of-two size when halving.
  Failed allocations do not create handles or enter the page allocator.
- Image and buffer storage assignment reject NULL before modifying the old
  storage/views. Constructors register the resource only after successful
  allocation, so a throwing constructor leaves no dangling registered object.
- The version string identifies `3.1.1-pes13-kit17`.

Real Vulkan allocation, mapping and release remain in use. This does not make
true out-of-memory conditions succeed: a DXVK allocation error can still reach
the game or terminate a worker. The objective is to reduce excess chunk demand
and avoid the observed NULL dereference. No Switch result or FPS gain is claimed.

The NRO remains byte-for-byte Kit15 and the FEX module remains Kit16. Graphics
quality, clock, shader policy and user settings are not changed by the package.
This remains a **32-bit no-alias** candidate. The separate [AS39 audit](AS39-LOW-WINDOW.md)
describes a potential larger-memory port, not functionality in this build.

## Validation

- Build and full source hash check against the pinned tree and submodules.
- Actual before/after allocator bodies, DXVK page allocator and resource storage
  bodies under ASan/UBSan with modeled Vulkan allocations: 768 pressure/recovery
  cases and 80 simultaneous live chunks, including a usable 26-page hole that
  the old minimum-size policy misses.
- Baseline NULL image/buffer storage faults reproduced under UBSan. Candidate
  assignments preserve old storage and reference counts when allocation fails;
  successful replacements and same-storage property changes also pass.
- PE32 dependency closure against the staged Wine runtime and its actual API-set
  schema: 58 PE files checked, no missing required/deferred modules or exports.
  This check validates imports, not full game execution or GPU behavior.

## Install and test

1. Close PES. Copy `switch/` from the package to the SD root and replace the five
   included files. Use the existing **32-bit no-alias NSP**.
2. Select **Default DXVK / DXVK 3.1.1**. GPL Async has a separate DLL and is not
   modified by this test. Preserve the same Medium preset, patch and clocks.
3. Use **Debug launch**, then Exhibition -> game plan -> kick-off. Return
   `fex-runtime.log` including on success. If it stops and HOME responds, allow
   about 15 seconds before closing.

All three D3D9 copies are necessary: the launcher renderer source, `C:\dxvk`,
and `C:\PES13`. Otherwise the launcher can restore the old renderer. Launcher
version remains `0.3.9-kit15`; the FEX log retains its Kit16 marker. Renderer
file hashes in `manifest.json` identify the new DLL. This build adds no logging
policy changes; ordinary Launch retains the existing production behavior.

Check runtime may report the experimental DLLs as changed. Repair runtime will
replace them; copy the candidate back if Repair is used. `rollback/switch/`
restores the Kit16 FEX, exact Kit15 NRO, and official DXVK 3.1.1. No ZIP, game,
Kitserver plugin, save or configuration file is included.
