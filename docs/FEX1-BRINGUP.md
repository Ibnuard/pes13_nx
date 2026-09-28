# FEX1: ARM64 module and Horizon JIT adapter

Branch: `experimental/fex-core`. This is the first implementation milestone of
the FEX port. It is **not yet a FEX version of the PES runtime**, and no FEX
gameplay or FPS result has been obtained.

## Implemented

- An isolated WSL build of official FEX commit
  `e2f973fe931e6dc2ce523795e51ca1ac3ca85816`, using LLVM-MinGW
  `20260505-ucrt-ubuntu-22.04-x86_64`. Target: ARM64 PE `wow64fex`, Cortex-A57,
  ARMv8.0. No Docker is used.
- A second, independently patched checkout/build for Horizon. The upstream
  DLL and the patched DLL are retained separately under ignored `local/fex1`.
- A versioned, size-checked C callback interface between the native host and
  the PE DLL. The DLL refuses JIT initialization without this interface.
- A native executable-memory adapter using libnx CodeMemory. FEX retains RX
  addresses as canonical code addresses; writes use the separate RW mapping.
  This preserves PC-relative branch calculations. Cache maintenance cleans
  the RW address and invalidates the RX address.
- Adaptations for FEX emitter writes, forward-label binding, code-buffer
  copies, direct/indirect block linking, unaligned-access backpatching, and the
  in-code backpatch lock. Returning an RW address as the code address would
  have broken those paths.
- A shared 32-bit allocation policy instead of FEX Windows' requirement to
  allocate native memory above the guest's 32-bit address space. Wine still
  chooses and validates allocations; no successful allocation is fabricated.
- A conservative Cortex-A57 host feature profile without a dependency on
  Windows' ARM64 hardware registry. Optional LSE/RCPC/SVE instructions remain
  disabled. This profile is for bring-up, not a tuned FEX performance preset.
- A standalone Switch NRO that uses the patched FEX emitter buffer and the
  same native adapter. It emits ARM64 code returning 42, backpatches it to
  return 85, checks alias bounds, and exercises mapping release/reuse.

The normal Box64 runtime and PES package have not been replaced. No game
executable, game asset, registry export, DLL, NRO, or upstream checkout is
added to Git.

## Validation and its limits

Both upstream and adapted ARM64 DLLs build. The import checker resolves the
module's **127 imports** against `wow64.dll` and `ntdll.dll` in the existing
`local/perf16/import-stage/drive_c/windows/system32` payload, then follows the
reachable dependencies. There are no missing imports in that static check.
This identifies the exact reference DLL hashes in its JSON report; it does
not establish behavior of an arbitrary SD installation or dynamically loaded
APIs.

The host test uses real, separately protected RX and RW mappings. It checks
alias offsets, invalid and overflowing ranges, foreign pointers, the actual
FEX forward-branch emitter, generated native host-code execution before and
after a patch, allocation exhaustion, reuse, and concurrent slot retirement.
It runs with AddressSanitizer and UndefinedBehaviorSanitizer. On the x86_64
WSL host, ARM64 instructions are checked as bytes; the native execution test
uses x86_64 instructions. **That is not FEX guest execution.**

The standalone NRO is cross-built with devkitA64/libnx and includes a validated
256x256 JPEG icon and NACP. The user's on-device log received on 2026-09-24
ends with `[FEX-PROBE] PASS result=0`: generated ARM64 execution, backpatching,
mapping bounds, pool exhaustion, release and reuse passed on the Switch.
The supplied evidence is archived locally as `local/fex2/fex1-hardware.log`.
The NRO tests ARM64 execution using the adapter; it does not include the Wine
loader or execute an x86 guest through FEXCore.

The final page of the shared code buffer remains excluded by FEX's bounded
allocator. A Wine `VirtualProtect` guard on this CodeMemory mapping is omitted
because Wine does not own that mapping. The temporary compilation buffer's
separate guard page is retained. This difference is explicit; the adapter
does not pretend to provide an OS guard that is absent.

## Reproduce in WSL

The LLVM-MinGW toolchain must already be installed under
`$PES_BUILD_ROOT/toolchains/llvm-mingw-20260505-ucrt-ubuntu-22.04-x86_64`.
`PES_BUILD_ROOT` defaults to `~/.cache/pes13-nx` when omitted.

```sh
python3 tools/build-fex-module.py --build-root "$PES_BUILD_ROOT" --jobs 4
python3 tools/build-fex-module.py --build-root "$PES_BUILD_ROOT" --jobs 4 --horizon
python3 tools/build-fex-probe.py --build-root "$PES_BUILD_ROOT"
python3 tools/audit-fex-imports.py \
  local/fex1/horizon-module/libwow64fex.dll \
  local/perf16/import-stage/drive_c/windows/system32 \
  --output local/fex1/horizon-module/import-audit.json
```

Import auditing needs `pefile` from `requirements.txt`; it can also run in
Windows Python. Build/test scripts run in WSL. The patcher checks the pinned
revision, exact upstream anchors and existing file contents before writing.
It refuses unexpected modifications and leaves the upstream control tree
unchanged.

Generated evidence:

| Path | Contents |
| --- | --- |
| `local/fex1/module/build.json` | Upstream DLL identity |
| `local/fex1/horizon-module/build.json` | Adapted DLL and adapter source hashes |
| `local/fex1/horizon-module/patches.json` | Before/after hashes of FEX changes |
| `local/fex1/horizon-module/import-audit.json` | Exact DLL imports and reference payload hashes |
| `local/fex1/probe/host-tests.txt` | Host test output |
| `local/fex1/probe/verification.json` | Probe NRO/package hashes and validation scope |
| `dist/pes13-fex1-jit-probe.zip` | Standalone hardware probe |

## Hardware probe

Copy the ZIP's `switch` directory onto the SD card, then launch:

```text
sdmc:/switch/pes13-fex-probe/pes13-fex-jit-probe.nro
```

Use full application mode. For a separate Sphaira forwarder, use the same
32-bit address space / no alias / 4-core settings as the current PES runtime.
The probe writes `switch/pes13-fex-probe/jit-probe.log`. A completed test ends
with `[FEX-PROBE] PASS result=0`; press `+` to leave. If it cannot obtain
simultaneous RW/RX CodeMemory mappings, it reports failure instead of using a
different JIT mechanism. The game directory and settings are not accessed.

## Next integration work

The loader, exception bridge and original x86 test are now implemented in
[FEX2](FEX2-BRINGUP.md). The list below records the integration requirements;
on-device guest validation is still pending.

1. Add a dedicated FEX backend value to Wine's native loader and `wow64.dll`.
   The current native bootstrap still explicitly selects `winebox64.dll`.
   Resolve and install `PES13FexSetHost` before `BTCpuProcessInit`, with matched
   native and PE builds. Selecting FEX before that work is not supported.
2. Bridge Horizon exceptions to the FEX Windows fault handler: lazy lookup
   table commitment, call/return stack guards, unaligned atomics, and guest
   self-modifying code notifications. The current fatal-exception path is
   Box64-specific. Existing context restoration borrows x17/x9; those scratch
   assumptions must be checked against FEX's register allocation, including
   vector registers and FPCR/FPSR preservation.
3. Verify WOW64 initialization, TEB/TLS, syscall/unixcall transitions, thread
   creation/suspension and teardown with small original x86 test programs.
   A name-only overlap of `BTCpu*` exports is insufficient.
4. Run PES only after those tests pass; then compare the same match sequence,
   resolution, graphics settings and clocks with the saved Box64 build.

FEX's Windows/WOW64 interface makes this route viable to investigate. The
remaining work is a platform integration, not a DLL-name or preset change.
The current results establish compilation and the tested adapter mechanics;
they do not establish that FEX boots PES, fixes event slowdowns, or reaches
30/60 FPS on Switch.
