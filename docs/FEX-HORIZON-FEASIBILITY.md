# FEX experiment for PES13-NX

This is a feasibility plan, not a performance result. The reference checkout
is official FEX commit `e2f973fe931e6dc2ce523795e51ca1ac3ca85816`
under ignored `local/fex-probe/upstream`. Do not bundle FEX into a release
before its build, license notices, boot behavior, and A/B results are verified.

## Integration point

PES13-NX already has the x86 game, an ARM64 Wine/WOW64 runtime, a working
`winebox64.dll` BT module, and DXVK/NVK. FEX's
[`Source/Windows/WOW64/Module.cpp`](https://github.com/FEX-Emu/FEX/blob/main/Source/Windows/WOW64/Module.cpp)
implements the same **family** of `BTCpu*` entry points as an ARM64 Windows
PE DLL. The [upstream package recipe](https://github.com/FEX-Emu/FEX-ppa/blob/main/deb_wine_base/rules)
builds this module with llvm-mingw. A first port should therefore target the
existing Wine WOW64 boundary: keep the PES13 environment and graphics stack,
and try a FEX BT module in an isolated build. This is less invasive than first
porting the entire Linux FEX emulator or standalone FEXCore application to
libnx. It still requires compatibility work inside Wine and perhaps FEX.

The Wine source already defaults ARM64+x86 WOW64 to `libwow64fex.dll` and
already looks up FEX's optional memory notification exports. Our Switch
bootstrap overrides that selection and preloads `winebox64.dll` explicitly in
`dlls/ntdll/loader.c`; it also sets `__wine_switch_cpu_backend` in
`dlls/wow64/syscall.c`. An experimental FEX path therefore needs a matched
Wine/bootstrap change as well as a new DLL. Merely copying a FEX DLL to the
SD card cannot switch backends.

The upstream [top-level CMake build](https://github.com/FEX-Emu/FEX/blob/main/CMakeLists.txt)
rejects `CMAKE_SYSTEM_NAME=Horizon` and GCC. That result only rules out a
direct build of upstream FEX as a native Horizon target with our current
devkitA64/GCC setup. It does **not** rule out an ARM64 PE WOW64 module compiled
with llvm-mingw and loaded by the existing Wine runtime.

## ABI snapshot

Run `python tools/check-fex-wow64-abi.py` after the ignored FEX checkout and
Wine spec are populated. The name-only comparison of the current
`winebox64.spec` with `libwow64fex.def` gives 16 shared names, one
Wine-only name (`BTCpuTurboThunkControl`), and seven FEX-only names. The latter
include `BTCpuNotifyMemoryAlloc`, `BTCpuNotifyMemoryDirty`,
`BTCpuNotifyMapViewOfSection`, and `BTCpuNotifyReadFile`. Signatures, call
ordering, and Wine version behavior have **not** yet been matched. The WOW64
source has optional call sites for several of these; the current Box64 module
simply does not export them. This is promising, but an export shim alone cannot
guarantee correct code-cache invalidation for PES13's loader,
self-modifying code, or changed memory protection.

## Milestones and stop conditions

1. Build the upstream `wow64fex` ARM64 PE module with llvm-mingw in a separate
   output tree, then list its imports and verify they resolve in this Wine
   build. No FEX binary or copyrighted game assets go into git.
2. Change the native bootstrap to select the FEX DLL in the experiment,
   compare each `BTCpu*` signature and lifecycle, and implement any missing
   notification or adapter. Keep the Box64 build untouched as a control and
   rollback.
3. Test tiny 32-bit x86 programs for process/thread startup, TLS/FS, x87/SSE,
   exceptions, syscall/unixcall transitions, executable memory changes, and
   repeated cold launches before starting PES13.
4. Only then test PES13 boot, a fixed menu scene, team selection, kickoff,
   replay, and the known late slowdown. Compare Box64 and FEX at the same
   1280x720 settings and CPU/GPU/RAM clocks, using frame times and CPU/driver
   counters rather than subjective FPS alone.

If the PE path proves blocked by unavailable Wine APIs or Horizon JIT memory
semantics, the fallback is a larger native FEXCore/Horizon integration. That
would need a Clang/libnx toolchain, executable-memory and instruction-cache
support, host thread/fault adapters, and a custom WOW64 bridge.

The [FEX README](https://github.com/FEX-Emu/FEX/blob/main/Readme.md) lists an
ARM64 Linux host and an ARMv8.0 feature baseline. We still need an on-device
feature probe and benchmark for Switch's Cortex-A57. FEX may improve the
CPU-bound path, but it has not been run in this project and does not establish
a 30 or 60 FPS outcome.
