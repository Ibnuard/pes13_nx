# FEX2: Wine loader and original x86 guest test

FEX1 passed on the user's Switch on 2026-09-24. That established the native
dual-mapping JIT adapter, ARM64 emission, execution, patching and reuse. It did
not execute an x86 guest. On 2026-09-24, the compact-heap FEX2 build passed
all 12 original x86 guest checks on Switch and exited with code 0. Its native
register/exception, allocator, counter and callback ABI preflights also pass.
The [hardware result](FEX2-RESULT.md) records the evidence and exact package
identity. **This establishes bounded guest execution, not PES compatibility
or a game performance result.**

## Previous allocation failure and compact heap fix

The ABI-fix run passes `[FEX2-ABI]`, allocation and timer preflights and process
CRT initialization. The TEB register remains valid at the fault (`x18=0x54fe0000`).
The next allocation requests `0x20000000` bytes (512 MiB), reserve/top-down,
and fails with `STATUS_NO_MEMORY` (`0xc0000017`). The largest kernel free range
reported is 447 MiB. Wine then faults writing NULL in its memcpy implementation:
`PC=0xffd19964`, ntdll RVA `0x69964`; FEX return RVA `0x762c` is in the
`fextl::string` growth path. This establishes failure to find contiguous virtual
address space; it does not establish exhausted physical RAM.

The pinned rpmalloc revision `09142d726429416bfa7b459151515fe3ab7622dd` uses
256 MiB spans. `os_mmap` reserves the span size **plus another span for
alignment**, so even a 24-byte allocation triggers a 512 MiB reservation.
This desktop layout is unsuitable for the forwarder's shared native/guest
32-bit address space. The Horizon build now uses 32 MiB spans and 32 MiB large
pages, retaining the existing allocator, size classes, thread caches, alignment
masks and commit/decommit paths. Each normal span reserves 64 MiB including
padding; the initial small/medium/large pages commit 64 KiB / 4 MiB / 32 MiB.
Large allocations above the 8 MiB size classes retain their separate huge-block
path and may request more, according to the caller's actual allocation size.

The first smaller candidate failed the local 8 MiB free test because a page
could contain only one block, a case the pinned free-list path does not handle.
It was not packaged. The final geometry has at least two blocks in every
normal size class, enforced along with power-of-two span/page constraints by
compile-time assertions. Changes apply only to the pinned rpmalloc submodule
in the isolated Horizon checkout. The patcher checks both the recorded gitlink
and actual submodule revision and rejects unexplained edits before writing.

Reserve/commit failures in this private heap now stop with `[FEX2-HEAP] STOP`
before callers can write through NULL or an uncommitted page. The diagnostic
does not allocate or use CRT formatting. Ordinary Wine VirtualAlloc failure
semantics and caller constraints are unchanged. A post-CRT `[FEX2-HEAP]`
preflight exercises real small, medium and large blocks before configuration
loading. The native NRO, WOW64 DLL and guest are unchanged.

`tests/fex_heap.py` runs the compiled allocator with two bounded free holes
derived conservatively from the log. Reserved pages are inaccessible until
committed; decommit zeroes and revokes access. The old DLL reproduces the
512 MiB failure for a 24-byte request. The corrected DLL passes the heap
preflight and executable-path construction, allocation boundaries from 1 byte
through 20 MiB, live growth over multiple spans, usable-size/data checks,
realloc, alignment, calloc, and two deterministically interleaved thread heaps
with cross-thread frees and reuse. Forced reserve/commit failures produce the
heap stop diagnostic. Wine memory helpers execute from the matched ntdll; OS
and path APIs are modeled. This is not simultaneous thread stress or a Switch
VM emulation. All previous regression suites also pass on the new DLL.
The subsequent hardware run passes this heap preflight, reaches first x86
dispatch and completes the guest test. Concurrent allocation/fault stress and
game performance remain unverified.

## Previous hardware result and callback ABI fix

The counter-fix hardware log passes `[FEX2-TIMER]` at 19.2 MHz and reaches
`[FEX2] process CRT ready` followed by `thread handlers`. The next exception
is a read at `PC=0xffcf211c`, `FAR=0x60`, with `x18=0`. In the bundled ARM64
ntdll at `0xffcb0000`, RVA `0x4211c` is `ldr x8, [x18, #0x60]` in
`LdrGetDllFullName`: read the PEB pointer from the current TEB. The caller is
FEX's `GetExecutableFilePath`, return RVA `0x112ad4`. This is a native PE
startup fault, not a guest x86 instruction or a frame-rate measurement.

[Windows ARM64 reserves x18 for the TEB](https://learn.microsoft.com/en-us/cpp/build/arm64-windows-abi-conventions?view=msvc-170).
The previous adapter called Horizon's function pointers directly, including
tail-calling its logger. Although our native Wine code uses `-ffixed-x18`,
that does not rebuild precompiled libraries with the same register contract.
The linked path `wine_nx_runtime_trace -> log_line -> vsnprintf -> _svfprintf_r`
uses x18 for formatting temporaries in newlib. The five host callbacks must
preserve the Windows register contract across their entire native call tree.

`module_host_call.S` now captures the incoming x18 in nonvolatile x19, invokes
the native callback, and restores x18, x19, the frame and return address. It
uses an aligned per-call stack frame with ARM64 PE unwind metadata; there is
no global TEB cache. Logging, executable allocation/release, writable-alias
lookup and cache flush all use this boundary. The ABI layout/version remains
unchanged. C++/SEH unwinding across a native callback is not supported by this
C ABI; callbacks return normally and hardware faults use the separate bridge.
`[FEX2-ABI]` checks a nonzero Wine TEB and its preservation over native logging
before process CRT initialization. No per-call logging is added to JIT writes.

`tests/fex_abi.py` runs the linked DLL with callbacks that overwrite native
volatile registers. It verifies every callback, arguments/results, failure
statuses, distinct incoming thread values, nested callbacks and the complete
CRT initializer. A second path executes the **actual native logger/formatter**
from the tested ELF, with console/SD output disabled and newlib thread storage
modeled. The old DLL loses x18 to a stack temporary; the corrected DLL retains
the TEB through CRT and thread setup. Separately, a callback modeled to leave
x18 zero reproduces the **exact Wine fault RVA `0x4211c`** from the hardware
log. The corrected DLL passes that TEB/PEB read in the actual Wine loader
prologue. The test does not simulate the later console/I/O call tree or the
whole loader, and does not claim guest execution. The latest Switch run now
confirms `[FEX2-ABI] PASS` and a preserved TEB at the later heap failure.

## Previous hardware result and counter fix

The next log confirms `[FEX2-ALLOC] PASS`. The subsequent exception has
`PC=0xff693d80`, module base `0xff5d0000`, hence RVA `0xc3d80`, and
`STATUS_ILLEGAL_INSTRUCTION`. In the exact tested DLL that is the first
instruction of `_GLOBAL__sub_I_JIT.cpp`: `mrs x8, CNTVCT_EL0` (`0xd53be048`).
Clang emitted it for `__builtin_readcyclecounter()` used to seed the JIT's
RDRAND fallback. FAR is not a valid memory-fault address for this exception.

Horizon applications use the physical system counter, `CNTPCT_EL0`, and
`CNTFRQ_EL0` for its frequency, as implemented by
[libnx's counter API](https://github.com/switchbrew/libnx/blob/master/nx/include/switch/arm/counter.h).
The corrected FEX build uses that clock domain for the initial seed, profiling,
timed locks, and the generated CycleCounter IR operation used by RDTSC/RDTSCP
and the Windows performance-counter pseudo-op. Requested ISB ordering is
preserved; no virtual-counter instruction or ECV-dependent timer is emitted
by that operation. The existing CPU feature baseline stays unchanged.

Before CRT initialization, `[FEX2-TIMER]` checks frequency and monotonic tick
progress and logs a result without using CRT formatting. It stops explicitly
if the timer is stationary, moves backwards, or reports zero frequency.

`tests/fex_counter.py` reproduces the old exception at the exact hardware RVA
while running the full CRT initializer. The corrected DLL completes CRT
initialization with bounded NT API mocks. Tests also run the **linked JIT
lowering method**, inspect its output and execute the resulting physical
counter reads for three destination registers with both ordering modes. All
executable sections are checked for leftover virtual-counter reads. These
instruction/API-model tests were followed by the successful physical-counter
and CRT checkpoints in the latest Switch log. Guest execution remains unproven.

## First hardware result and allocation fix

The supplied `fex-runtime.log` contains `[FEX2-HOST] PASS`, successful loading
of the ARM64 FEX DLL and host ABI installation, then a write fault at
`PC=0xff78fcc4`, `FAR=0x7f0`, with FEX based at `0xff5d0000`. RVA `0x1bfcc4`
is `get_thread_heap_allocate`: `str xzr, [x20, #0x7f0]`, with `x20=0`.
The failed allocation was only 4 KB; this result does not establish RAM
exhaustion or a JIT execution fault.

The initial Horizon adapter added an address requirement with upper bound
`UINT32_MAX`. Wine's `get_extended_params` rejects that bound because the
WOW64 limit is `0xffff0000`, returning `STATUS_INVALID_PARAMETER` (`0xc000000d`).
The allocation returns NULL and rpmalloc dereferences it. This is consistent
with the [Windows address-requirement contract](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-mem_address_requirements):
an explicit upper bound must not exceed the maximum application address.

The corrected FEX DLL uses `NtAllocateVirtualMemory` for ordinary allocations
and passes the caller's parameters unchanged to `NtAllocateVirtualMemoryEx`.
Wine retains responsibility for address limits and mapping conflicts. Invalid
caller constraints and out-of-memory failures are still reported as failures.
No VM validation is disabled. A no-CRT diagnostic records failed allocation
parameters and status. Before rpmalloc initializes, a small reserve/commit/
write/free test and an extended aligned allocation must pass.

`tests/fex_alloc.py` executes both DLLs under Unicorn with a bounded NT API
model. The old DLL reproduces **the exact hardware fault RVA**; the corrected
DLL completes the allocation preflight, preserves caller alignment, rejects
invalid bounds, reports forced allocation failures, and runs rpmalloc's
initialize/allocate/free/thread-finalize paths. This validates the compiled
DLL behavior against the modeled API contract, not Horizon's VM service.
The native NRO, WOW64 DLL and original x86 guest are unchanged in this fix.

## Implemented

- Separate native Wine and PE Wine source/build snapshots under
  `fex-experiment/wine2`. The existing Box64 build sources are not edited.
- Explicit FEX backend identifier `0x46455832`, matched between the native
  bootstrap and the rebuilt ARM64 `wow64.dll`. The loader selects
  `libwow64fex.dll`, installs the host ABI before CPU initialization, and
  requires the exception export. The NRO is built without the Box64 engine.
- A `PES13FexHandleException` export that passes Wine exception/context records
  to FEX's Windows handler. Null thread state during initialization is guarded;
  failed lazy commits are no longer reported as successful fault recovery.
- ESR decoding distinguishes memory faults, unaligned atomics, illegal
  instructions and breakpoints. Wine handles ordinary VM faults first; FEX
  handles its own lazy tables, call/return guard, backpatches and guest code
  invalidation. Unhandled faults remain failures and retain diagnostics.
- Full ARM64 context restoration. The old runtime resumed through x9/x17,
  which FEX may use for guest state. A private UDF at one exact instruction
  address now re-enters Horizon's exception protocol, writes the requested
  kernel frame, restores the remaining GPRs/NEON/FP state and returns with
  `svcReturnFromException`. It does not discard a live register. Ordinary
  exceptions delegate to the installed libnx entry, linked under a private
  symbol; the installed libnx library is not modified. The implementation
  follows the frame contract in [libnx's exception entry](https://github.com/switchbrew/libnx/blob/master/nx/source/runtime/exception.s)
  and [context definitions](https://github.com/switchbrew/libnx/blob/master/nx/include/switch/arm/thread_context.h).
- Native FEX helper threads requesting `SKIP_LOADER_INIT` enter the native
  thread path instead of being decoded as x86. Guest threads retain the WOW64
  path. This route still needs on-device lifecycle verification.
- A mandatory hardware context preflight before Wine starts: restore patterned
  registers, take an ordinary exception, and check every GPR, vector, NZCV,
  FPCR and FPSR after resuming. Failure prevents FEX startup.
- An original, CRT-free i386 executable testing integer arithmetic, FS/TLS,
  SSE, x87, a clock/wait syscall, executable page changes, translated code
  invalidation (42 to 85), CALL/RET and a worker's TLS isolation/termination.
  Every checkpoint is flushed to its own small log. Per-syscall tracing and
  game profiling are disabled; startup checkpoints are flushed immediately.

## Package and hardware procedure

Extract `dist/pes13-fex2-heap-fix.zip` to the SD root, replacing package files.
An existing FEX2 forwarder can be reused. It creates a separate
`switch/pes13-fex2` directory with one NRO, the original test, the required
Wine/FEX DLLs and NLS data. No game files, private registry, saves, settings.dat
or DXVK files are included. The existing `switch/pes13-nx` directory is not
used by this test. Do not mix DLLs between the two directories.

Launch `switch/pes13-fex2/pes13-fex2.nro` in full application mode. A separate
Sphaira forwarder uses the same **32-bit address space / no alias / 4 cores**
as FEX1. No overclock requirement or game FPS claim is attached to this test.

The expected progression is:

1. `[FEX2-HOST] PASS` in the console/runtime log.
2. `[FEX2-ABI] PASS`, `[FEX2-ALLOC] PASS`, `[FEX2-TIMER] PASS`, then
   `[FEX2] process CRT ready` and `[FEX2-HEAP] PASS`.
3. CPU initialization and `first x86 dispatch` markers.
4. `[FEX2-GUEST] PASS all checks` in the guest log, followed by exit code 0.

The runtime parks after process termination. Close via HOME → X → Close.
If initialization stops, allow up to 60 seconds, close it, and retain the
available logs. Return these files before another run overwrites them:

```text
switch/pes13-fex2/fex-runtime.log
switch/pes13-fex2/drive_c/fex-guest.log
```

The second log exists only after the x86 test reaches its first file write.
Host PASS alone, or a successfully loaded DLL, is not guest PASS.

## Local verification

- Both the native runtime/NRO and the adapted ARM64 FEX DLL compile; the
  matching PE `wow64.dll` and i386 test compile in WSL without Docker.
- `tests/fex_context.py` executes the **linked** restore instructions with
  Unicorn for three register patterns and checks the complete kernel frame,
  GPR/NEON/FP state and ordinary/null-frame delegation. It does not emulate
  Horizon's actual exception return; the hardware preflight covers that and
  has passed on the user's Switch with this native NRO.
- `tests/fex_guest_reference.py` runs the exact original guest executable on
  Windows, in a fresh workspace directory. All checks pass there. This
  validates the test program, not FEX or Horizon.
- Packaging checks native and guest import/export resolution against the exact
  bundled DLLs, architecture, host exports, file hashes, one-NRO layout, icon,
  NACP and ZIP contents. NLS/reference Wine files match the dependency allowlist.
- The package requires passing allocation, counter/CRT, callback ABI and heap reports
  for the exact corrected FEX DLL hash. The ABI report also identifies the
  native ELF and matched Wine ntdll used for the regression.

This milestone does not establish graphics, audio, PES initialization, guest
SEH coverage, suspend/resume, repeated-launch stability or concurrent fault
stress. The ordinary libnx exception path still uses its shared dump/stack;
per-thread exception storage must be addressed before general concurrent
fault handling or a production game build. The supplied guest exercises one
worker with a bounded wait, not a concurrent-exception stress workload.

## Reproduce

Prerequisites are the existing matched Wine-NX/PE/Mesa build cache, LLVM-MinGW,
devkitA64/libnx, and the pinned FEX source used by FEX1. `--build-root` refers
to that WSL cache. The scripts use isolated copies and reject unexplained
source edits. No Docker is used.

```sh
python3 tools/build-fex-module.py --build-root "$PES_BUILD_ROOT" --horizon \
  --output-dir local/fex2/module --jobs 4
python3 tools/build-fex-runtime.py --build-root "$PES_BUILD_ROOT" --jobs 4
```

On Windows, run the reference test and package. The assembly check takes the
current native ELF from `fex-experiment/wine2/native-build/wine-nx-runtime.elf`.
It requires pyelftools and Unicorn; import checks use pefile.

```text
python tests/fex_context.py <native-runtime.elf>
python tests/fex_guest_reference.py
python tests/fex_counter.py local/fex2/module/libwow64fex.dll --output local/fex2/heap-fix/counter-tests.json
python tests/fex_alloc.py local/fex2/module/libwow64fex.dll --output local/fex2/heap-fix/allocation-tests.json
python tests/fex_abi.py local/fex2/module/libwow64fex.dll --before local/fex2/abi-fix/libwow64fex-before.dll --native-elf local/fex2/reference/fex2.elf --ntdll local/perf16/import-stage/drive_c/windows/system32/ntdll.dll --output local/fex2/heap-fix/abi-tests.json
python tests/fex_heap.py local/fex2/module/libwow64fex.dll --before local/fex2/heap-fix/libwow64fex-before.dll --ntdll local/perf16/import-stage/drive_c/windows/system32/ntdll.dll --output local/fex2/heap-fix/heap-tests.json
python tools/package-fex2.py
```

Evidence is retained in `local/fex2`: FEX1 hardware input, source patch hashes,
build reports, reference results, import audits and package hash. The initial
crash input, old DLL and allocation regression result are in `local/fex2/alloc-fix`;
the counter crash input is in `local/fex2/counter-fix`, and the callback crash
input and previous DLL are in `local/fex2/abi-fix`. The 512 MiB failure input,
previous DLL and current reports are in `local/fex2/heap-fix`. Use
`--before <old-DLL>` with the corresponding test to reproduce its old fault.
The counter/ABI tests create the report directory for a clean build. All binaries
and logs remain ignored by Git. The first complete hardware PASS, its original
package, both logs, adapter source snapshot and build receipts are retained in
`local/fex2/hardware-pass-20260924`. The historical package's build-time
`on_device_tested: false` is preserved; `hardware-result.json` records the
later result separately. The next work is per-thread exception storage,
thread/fault stress and PES startup integration, followed by comparable frame
time measurements at fixed settings and clocks.
