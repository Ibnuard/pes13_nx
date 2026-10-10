# FEXTendo memory ABI v1 — experimental

The kernel and system loader select a low guest window from a versioned ExeFS
descriptor. There is **no game Title ID allowlist or Title ID range** in this
selection. Native code/backing memory uses the high part of a 39-bit process;
the guest mapping window starts at `0x00200000` and extends below 4 GiB.

This package is a boot/probe experiment. It is **not a new PES runtime** and does
not turn the current 32-bit-no-alias PES build into a compatible 39-bit build.
Wine/FEX/DXVK, each game's prefix, saves and presets remain separate per game.

## User workflow after the ABI has passed device testing

1. Install a compatible generic kernel/loader pair and reboot once.
2. Install a game's forwarder and copy that game's compatible runtime.
3. Install another compatible game without editing a Title ID list, rebuilding
   the kernel, switching a per-game boot entry, or rebooting for that new game.

Replacing the kernel or changing the ABI/system-version support can still
require a reboot. This does not implement live kernel patching. Each NSP still
needs its own noncolliding Title ID for installation; that ID does not decide
the process memory layout.

The full 4 GiB guest **address window is not 4 GiB of physical RAM**. The earlier
Sleeping Dogs hardware result exposed a 3285 MiB process quota and approximately
3.12 GiB of supplied heap. Memory available to a game remains subject to its
process quota and runtime allocations.

## Test package for this console

Reference system: HOS 22.5.0, Atmosphere 1.11.2, HOC 2.5.1. The HOC loader keeps
the supplied `hoc.kip` CUST configuration byte for byte. This particular HOC
binary is therefore a test build for that configuration, not a universal OC
configuration to distribute to other consoles.

Copy `atmosphere/`, `bootloader/` and `switch/` from the distribution root to the
SD root, then install the three NSPs under `forwarders/`. Boot Hekate's
**More configs → FEXTendo Memory v1 TEST** entry once.

Run these HOME tiles in order, closing each with `+` before starting the next:

| Tile | Expected behavior | Log |
| --- | --- | --- |
| FEXTendo Memory CONTROL | Low `0x00400000` and `0x00200000` mappings rejected; upper 32-bit RW roundtrip and native/JIT tests pass | `switch/fextendo-memory-probe/control.log` |
| FEXTendo Memory OPTIN-A | Low RX, RW → NONE → RW at both ends, native RX and JIT pass | `switch/fextendo-memory-probe/optin-a.log` |
| FEXTendo Memory OPTIN-B | Same tests pass under a different Title ID | `switch/fextendo-memory-probe/optin-b.log` |

All three tiles should finish with `[SUMMARY] PASS`. In the control run, the
low-address rejection is the expected result. Repeat A/B without rebooting to
check that selection follows each process's descriptor.

The probe logs its native address, actual supplied heap capacity and process
quota. It does not load a game or a Wine prefix. Diagnostic logging is confined
to this separate probe directory. Launching this NRO directly from hbmenu is
not an acceptance test: use the supplied HOME tiles.

The package adds a separate Hekate entry. It does not replace
`bootloader/hekate_ipl.ini`, `atmosphere/package3`, or the original `hoc.kip`.
Return to the previous Hekate entry to use the existing game forwarders.
In particular, Sleeping Dogs' older Title-ID-based low-window forwarder is not
implicitly enabled by this new generic pair: it needs a descriptor-bearing
replacement forwarder before it can use this entry. PES production still uses
its existing 32-bit-no-alias runtime/forwarder.

## Descriptor and process-creation interface

The forwarder builder packages a **32-byte ExeFS file named `fxtmem`**, not a
runtime INI file. All integers below are little endian.

| Offset | Size | v1 value |
| --- | --- | --- |
| 0 | 8 | `FXTMEM\0\0` |
| 8 | 4 | ABI version `1` |
| 12 | 4 | Descriptor length `32` |
| 16 | 4 | Layout `1`: low32 guest / native39 |
| 20 | 4 | Flags `0` |
| 24 | 8 | Reserved `0` |

The system loader reads the mounted code filesystem after NPDM validation and
before ASLR placement/`svcCreateProcess`. Missing descriptor preserves the
normal path. Malformed descriptors, unknown versions/layouts, I/O errors and
incompatible NPDM modes are rejected. The descriptor must request ARM64 native
code, 39-bit addressing, application type and application pool. Alias-region
extra-size mode is not supported by v1.

On the pinned base, the private process request is bit 30 (`0x40000000`) in
`CreateProcessParameter.flags`. **This is a private ABI between the matching
patched loader and kernel, not an upstream Atmosphere flag or an NPDM bit.**
The kernel checks compatibility independently and requires native process code
at or above `0x100000000`. Both the loader's ASLR floor and the kernel's native
region floor use that boundary; the AliasCode floor becomes `0x00200000` only
for opted-in processes. All other flags retain their existing meanings.

Applications must still reserve guest VA before allocating native aliases/JIT
memory. The forwarder uses a private 16 KiB BSS allocator for reservation
bookkeeping, keeps the low guest span reserved across NRO reloads, and places
native NRO code above 4 GiB. This carries forward the fix proven by the Sleeping
Dogs StartupFix work. A game runtime also needs its own early low-window guard,
high-backing/low-alias allocator, pointer-width audit and startup compatibility
check. Adding a descriptor alone is not a runtime port.

Before a production port uses this ABI, its preflight must confirm the expected
layout and low mapping permissions. A mismatched or unpatched loader may ignore
the descriptor; it must not be allowed to enter the game with an assumed layout.

## Validation and device results

Host tests execute the actual descriptor-reading code with injected filesystem
errors, every single-bit descriptor mutation and all 16,384 combinations of
the current process flags, both marked and unmarked. ASan/UBSan is enabled.
There are 65,836 cases. The real ARM64 forwarder runs in Unicorn with modeled
Horizon services, including low/high RNG candidates, NRO reload, allocation
failure and free. NSP checks parse the actual ExeFS and verify the marker is
absent from the control and present in A/B.

The kernel and both stock/HOC loaders are compiled. The packaging gate verifies
their source diffs, overlay hashes, HOC settings, NSPs and test receipts. These
checks alone do **not** prove that Horizon boots or that the new pair is
compatible with a physical console. The subsequent probe-r2 hardware results
below pass the generic mapping gate. PES integration and match testing remain
a separate gate.

### First device results and probe-r2

The supplied CONTROL, OPTIN-A and OPTIN-B logs confirm that the generic boot
pair selects the intended layout for two different descriptor-bearing titles:
A/B report `aslr_base=0x200000`, execute low RX code at `0x400000`, and pass
native RX plus FEX JIT/backpatch above 4 GiB. CONTROL reports the normal
`aslr_base=0x8000000` and rejects the two below-floor mappings. The measured
process quota is 3285 MiB and supplied heap is 3,321,602,048 bytes (about 3.09 GiB).
The reported 8 GiB heap *region* is virtual address space, not physical RAM.

Both opt-in summaries failed at `RW -> NONE`. The probe incorrectly reused
`svcSetProcessMemoryPermission` after its initial RW call had converted
AliasCode to AliasCodeData. That state has CanReprotect but no Code flag, so
the kernel correctly rejected the call with `0xd401`. The working Sleeping
Dogs implementation uses `svcSetMemoryPermission` for these subsequent data
permission changes. The probe-r2 update follows that sequence and logs only
permission calls it actually executes. Permission/data failures are distinct
from mapping rejection. CONTROL now also requires the upper-address roundtrip
to pass; its original summary incorrectly omitted that check.

Actual ARM64 binary tests reproduce the old failure and exercise the corrected
roundtrip with modeled Horizon services, including permission, data and cleanup
failures. They are not a substitute for rerunning the updated NRO on the console.
At that stage, the device acceptance gate remained open pending probe-r2 logs.

**NRO-only update:** copy `switch/` from `dist/fextendo-low-window-v1-probe-r2/`
onto the SD root. Keep the original three HOME tiles and v1 kernel/loader pair.
No new NSP installation or reboot is needed if still running the FEXTendo v1
test boot entry. Close each probe with `+`, then test CONTROL, A, B and A again.
The log header must include `probe-r2`. Logs remain in
`switch/fextendo-memory-probe/`. This update does not run or port PES.

### Probe-r2 hardware acceptance

The next supplied CONTROL, OPTIN-A and OPTIN-B logs all report `probe-r2` and
`[SUMMARY] PASS`. Both opt-in titles pass low RX at 4 MiB, RW/NONE/RW at 2 MiB
and `0xfffff000`, native high RX and FEX high JIT execution/backpatch. CONTROL
retains the ordinary 39-bit floor and passes its expected rejection tests.
The exact logs and SHA256 receipts are archived under
`local/fextendo-memory-probe-r2/device-pass/` and in the PES integration package.

This validates opt-in for different Title IDs without a per-title kernel
allowlist. It does not promise compatibility with every firmware/CFW version,
4 GiB of physical heap, or higher game FPS. The measured supplied heap remains
3,321,602,048 bytes (about 3.09 GiB).

PES integration is isolated in [PES13-LOW-WINDOW-V1.md](PES13-LOW-WINDOW-V1.md).
It reuses the tested generic forwarder binary with different target metadata,
keeps native libnx address selection above 4 GiB, and validates the ABI before
starting Wine. The game/prefix remain separate from other titles.

## Pinned sources and reproduction

- [Atmosphere 1.11.2](https://github.com/Atmosphere-NX/Atmosphere/tree/5388824be146a89619e8d641acd64599cf1c5f62)
- [Autorun low-window patch](https://github.com/autorunhq/autorun/blob/cbb0e4e6e7fa7f47f328d92441f51bfb507f266f/horizon-wine/mesosphere/low-window.patch)
- [HOC loader source](https://github.com/Horizon-OC/Horizon-OC/tree/d9906a794c6015a892c60744d520faf793d22549)
- [HOC 2.5.1](https://github.com/Horizon-OC/Horizon-OC/releases/tag/2.5.1)
- [Sphaira HBL base](https://github.com/ITotalJustice/sphaira/tree/72a94b905816de24817594109fb012a8f7107d8c)

The generated `boot/atmosphere-fextendo.patch` and
`boot/atmosphere-hoc-fextendo.patch` each apply directly to the pinned clean
Atmosphere commit. The HOC diff includes the matching HOC loader source and
version fix. The new header/reader sources, build scripts, forwarder source and
test receipts are included under `source/`; licenses are retained.

In this workspace, under WSL with devkitPro installed:

```sh
python3 tools/build-fextendo-low-window.py \
  --work /home/blekjek/fextendo-low-window-v1 \
  --cache /home/blekjek/sleepingdogs-low-window-v1
python3 tools/build-fextendo-memory-probe.py \
  --work /home/blekjek/fextendo-memory-probe-v1 \
  --keys /path/to/local/prod.keys
```

Use fresh isolated build directories when changing inputs. The cache contains
the pinned Atmosphere, HOC and hactool Git checkouts, the verified HOC release
archive and Autorun's version patch. No keys are copied to the distribution.
The boot helper preserves the user-supplied HOC configuration only after
checking its layout and verifying that the file differs from the pinned release
only within that settings region.

For the probe-only permission correction (no packing keys or kernel build):

```sh
python3 tools/build-fextendo-memory-probe.py --nro-only \
  --work /home/blekjek/fextendo-memory-probe-r2 \
  --output dist/fextendo-low-window-v1-probe-r2
python3 tests/fextendo_memory_probe_binary.py \
  /home/blekjek/fextendo-memory-probe-r2/memory-probe.elf \
  --before /home/blekjek/fextendo-memory-probe-v1/memory-probe.elf \
  --output local/fextendo-memory-probe-r2/binary-tests.json
```
