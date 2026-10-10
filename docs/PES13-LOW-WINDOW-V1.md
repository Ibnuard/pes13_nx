# PES13 low-window v1 (experimental)

This build integrates the generic `fxtmem-v1` memory layout into the existing
PES13 runtime. It builds from the frozen Kit15 native source and uses the same
Kit16 FEX module and Kit17 Default DXVK as the last cumulative package. It does
not change game speed, rendering presets, FEX optimization flags or OC settings.

The purpose is to remove native heap/JIT/driver address competition from the
x86 guest's below-4-GiB window and allow the larger 39-bit process heap. The
probe measured a 3285 MiB process budget and about 3.09 GiB supplied heap.
The 8 GiB virtual heap region is not 8 GiB of RAM, and this does not produce a
full 4 GiB physical heap. Allocation pressure inside the game may still occur.

## Runtime changes

- The first `virtmemSetup` excludes addresses below 4 GiB from native libnx
  stack/code/ASLR selection when the exact low-window layout is present. The
  existing reservation list and exhaustive free-range recovery remain in use.
- The launcher accepts only the verified low-window 39-bit layout for this
  NRO. It checks native code/heap/stack/TLS placement and mapping capabilities,
  then executes low RX and RW/NONE/RW probes before Wine creates guest views.
  Failed cleanup retains kernel-owned backing and rejects launch.
- Wine retains its existing high backing / low alias ownership and commit
  recovery. There is no software bias added to guest loads/stores and no new
  per-access translation step.
- The existing Vulkan WoW64 path uses low guest imports for host-visible
  buffers in a 39-bit process. It must not use the 32-bit-only direct native
  pointer shortcut. The Vulkan/DXVK implementation itself is unchanged.
- Normal launch keeps diagnostic file output disabled. Debug launch records
  `[PES13-LOWVA] v1 ready=1 ...` with the actual supplied heap and process budget.

## Installing and testing

1. Use the same generic **FEXTendo Memory v1 TEST** boot entry that passed
   CONTROL/A/B probe-r2. This package does not replace Atmosphere, the loader,
   bootloader configuration or OC settings. No reboot is needed if still in
   that entry; return to it first if you changed entries.
2. Copy this package's `switch/` folder to the SD root. The new runtime is
   `/switch/pes13-fex/pes13-low-window.nro`; it sits beside the old
   `pes13-fex.nro`. The included FEX/DXVK files are identical to Kit17's
   cumulative runtime. Keep the existing full runtime, game and configuration.
3. Install `forwarders/PES13-Low-Window-v1.nsp` once. Its HOME name is
   **PES13 Low Window**, Title ID `05c87a7fe7cff000`. It requests the generic ABI
   through its `fxtmem` descriptor, without a new kernel allowlist entry.
4. Open that HOME tile, confirm launcher version **0.3.9-lw1**, select
   **Default DXVK** and enable/select **Debug launch** for the first test.
   Preserve the graphics preset and CPU/GPU/RAM clocks used in the previous
   Kitserver test so the comparison is useful.
5. Test startup, Exhibition, controller selection, team selection, gameplan,
   prematch and kick-off. If those work, continue through ball-out, replay and
   halftime/full-time transitions. Close through HOME after the test and copy
   `/switch/pes13-fex/fex-runtime.log`; include `crash.log` if one was written.
   Note the screen/phase where progress stops if it fails.

The ordinary PES HOME tile still loads the original `pes13-fex.nro`. Use it to
return to the 32-bit baseline. If that NRO had been replaced separately, the
package also contains the exact Kit15 baseline under `rollback/switch/`.
The game files and Wine prefix are shared between these two PES test tiles,
but remain separate from other games. No game/save/INI files are distributed.
Runtime Fixer repair can restore release DLLs; if used, recopy this package's
runtime files before comparing builds.

## Validation scope

The generic probe has passed on the supplied device logs for CONTROL and two
independent opt-in Title IDs. The new PES native ELF also passes focused tests
that execute actual ARM64 under Unicorn with modeled heap/SVC/services:

- Fully relocated high native code executes the complete preflight, including
  generated ARM64 at 4 MiB and data reprotection at the bottom/top guest pages.
- Allocation, mapping, permission, data and unmap failures reject launch;
  failed unmap never frees kernel-owned pages. Preflight runs only once.
- Actual libnx pre-main preserves a loader-supplied heap larger than 3 GiB and
  excludes ordinary 32/36/39-bit launch modes from the fixed guest preload.
- Native address search/recovery never falls into the low guest window.
- Wine maps/protects/releases low views backed by pointers above 4 GiB and
  retains commit ownership when an injected allocation/mapping failure occurs.
- Normal diagnostic paths do not perform file I/O; the low-window report is
  captured only when Debug launch is enabled.

The packaged NSP's actual ExeFS, descriptor, NPDM, architecture, address mode,
target path and title identity are parsed and verified. Its NSO is byte-for-byte
the forwarder that passed probe-r2; only package metadata/target differ.

**PES gameplay on this build has not yet been tested on Switch.** Host checks
do not establish improved FPS or that all Kitserver memory failures are fixed.
See `package.json`, `evidence/`, `source/` and `SHA256SUMS.txt` for receipts.
