# FEXTendo 0.3.8-r6: production launch and CPU virtual-address recovery

The runtime retains the native memory recovery from checkpoint
`d2c93a7d3233274ea856ebf88f158d4f4f828ec9`. That checkpoint completed a
90-minute match in game time for the user. Revision r3 introduced the two
launch paths below. Revision r5 extends recovery to Mesa's C allocator, reclaims
idle Wine arenas under pressure and corrects concurrent alias retirement.
r6 extends CPU data aliases beyond the native stack region and adds exhaustive
VA search after random misses. On October 5, 2026, the user reported that r6
was safe so far on their Switch and requested this checkpoint. This is initial
device feedback: the test duration and completion of a full HIGH match were
not specified. All 28 local validation groups passed for the delivered binary.
Its NRO SHA-256 is
`9d5acf823e5494f5d04e8b5ebd7cd54487e5033de4df09be3e8e76db1cf9eb06`.

Subsequent feedback reports intermittent freezing on HIGH with the latest r6
NRO: some runs succeed, while others stop during a PES transition overlay and
audio repeats. No matching r6 failure logs have been supplied for this report.
The earlier successful session is a checkpoint, not validation that HIGH is
fixed. The screenshot locates the visible stall but cannot identify allocation
failure, a parked exception thread, or a synchronization stall as its cause.

## r5 evidence and r6 changes

The latest PE/crash.log matches the delivered r5 build ID
`e487ca7d5b15d47b1e3d9bd977644bea509ddc7e`. At runtime time 142.901 s,
the FIRST failure is `owner=scratch bytes=16777216 pages_stage=6 rc=0`.
Stage 6 is the NULL result from `virtmemFindStack`; physical source fragments
were allocated successfully, but no destination was selected. Rollback releases
them. The subsequent diagnostic reports 97626464 bytes of free libc heap,
7921664 untaken heap bytes and 8 MiB left in the 64-MiB reserve (56 MiB used).
Then FEX's compiler deliberately stops and the exception handler parks it.
There is no earlier Mesa NULL exception in this run.

Startup records the actual stack window `0x00200000..0x40000000`, ASLR window
`0x00200000..0x100000000`, and excluded heap `0x41e00000..0xc1e00000`.
Early Wine reservations protect 509 MiB from native placement, and JIT aliases
also occupy parts of the remaining address space. Free physical bytes do not
imply a free contiguous virtual interval. r5 searches only the stack window,
and its linked libnx finder gives up after 512 random candidates. This log
cannot distinguish a fully fragmented stack window from a missed valid hole;
it also does not capture an exact complete map of high-ASLR free spans.

r6 addresses both limitations for all shared CPU recovery sizes:

- FEX scratch/lookup/private heap and native Mesa/Rust recovery use the existing
  Wine process-code mapping protocol across the legal ASLR region, with **RW
  permission only**. It creates no per-fragment kernel handles, executable
  data pages or extra resident reserve. Each piece's successful map is recorded
  before permissions are applied so a permission failure rolls back that piece
  too. Failed rollback retains the entire owner, sources and reservation.
  Hosts lacking those syscalls retain the stack protocol.
  Find/reserve/map/permission are one critical section under the original
  libnx lock. Wine's fixed-address path checks kernel occupancy under that lock;
  releasing it before mapping would expose an unmapped reservation to that
  check. Rollback drops the lock before owner cleanup, preserving lock order.
- The libnx-compatible manager keeps a single original reservation list, mutex
  and region setup. Normal random search remains; after it misses, a bounded,
  monotonic walk checks every kernel-unmapped interval against heap/alias
  exclusions, guards and ALL software reservations. It cannot overwrite a
  reserved Wine/JIT/thread range just because the kernel reports it unmapped.
  The local object supplies the full virtmem ABI, so the SDK's original
  `virtmem.o` is not also linked. Installed SDK libraries remain unchanged.
- Rare debug allocation reports add cumulative `va_scan`, `va_ok`, `va_fail`
  and `va_largest` (usable span from the last scan; it may belong to another
  thread). There is no new worker or per-frame memory query.

The exact old/new ARM64 binaries are exercised with the logged region sizes,
a full stack window, a modeled 40-MiB high-ASLR hole and 512 deliberately missed
random probes. r5 fails the 16-MiB request; r6 maps all fragments RW and releases
them. Additional checks cover a reserved hole, true exhaustion, permission
failure, rollback quarantine, and 32 independently computed interval layouts.
The fixture reproduces the code limitation; it is not a reconstruction of
every unrecorded mapping on the user's Switch and does not prove HIGH stability.

References: [libnx virtual memory manager](https://github.com/switchbrew/libnx/blob/master/nx/source/kernel/virtmem.c)
and [Atmosphere process mapping and permission implementation](https://github.com/Atmosphere-NX/Atmosphere/blob/master/libraries/libmesosphere/source/kern_k_page_table_base.cpp).
The copied libnx source digest and ISC notice are in `fextendo_virtmem.c`.
The matching r5 ELF independently confirms the 512-attempt finder.

## r4 evidence and r5 changes

The preceding PE/crash.log matched r4 build ID
`977aed5d0449dd96a9f63c223dd93adb4c3fa12a`. The FIRST exception is at 129.760 s:
native NRO RVA `0x4a5744`, `linear_alloc_child+4`, reads NULL+4. Its caller is
`vtn_create_builder+0xc8`. Registers and exact disassembly reconstruct SPIR-V
bound 621, a 90112-byte linear buffer, and a **90192-byte libc allocation**.
`linear_context_with_opts` returns NULL on failed malloc; its caller does not
check it. The shader-compilation thread is then parked by the exception path.
Only later, at 365.144 s, does a FEX worker fail to acquire 16 MiB of scratch.
These are distinct failures; neither the startup heap reservation nor these
records alone prove physical RAM exhaustion. The old log does not capture
fragmentation, free heap or failure stages at the first Mesa allocation.

r4 protected private FEX and Rust allocations but **not the C ralloc/linear/GC
family in Mesa**. r5 redirects malloc/realloc/free imports of the hash-pinned
ralloc object to CPU recovery. An explicit object is linked before archives;
reversing the three symbol renames reproduces the original object byte for byte.
The installed libraries, GPU buffer allocator and compiled shader instructions
are untouched. There is no process-wide malloc interception or new ralloc ABI.
Normal requests keep libc malloc/realloc/free; failed requests use the shared
fragmented page store and, if possible, idle pages of the existing 64-MiB reserve.
Realloc preserves data and the original owner on failure. Native C and Rust
fallbacks record size and ownership; no alias is passed to libc realloc/free.

Under allocation pressure, a non-blocking Wine callback returns completely idle
2-MiB backing arenas to libc. Partial/live/mapped arenas remain intact. A pool
with holes now searches all existing arenas before trying to allocate another.
This benefits FEX scratch/private containers and native CPU allocations without
enlarging resident pools or polling memory every frame.

Fault-injected parallel CPU allocation tests also exposed an address-reuse bug:
an old RELEASING record could swallow the free of a new allocation using the
same virtual address. r5 retires lookup ownership BEFORE removing the virtual
reservation/returning reserve pages. Metadata stays unavailable for reuse until
source disposal finishes. Failed unmaps still retain their quarantine ownership.
A deterministic test reissues and frees the same address during that exact
teardown window; randomized concurrent growth/free exercises it as well.

Debug-only pressure records now cover scratch and native CPU failures as well as
private FEX containers. They include page stage, kernel result, heap free bytes,
reserve occupancy/largest span and trimmed bytes. Recovery is still bounded:
128 shared owners and 128 MiB of page recovery; reserve loans also consume owner
metadata and need available reserve pages. Real exhaustion, unavailable VA or
kernel mapping refusal can still fail. Local tests do not establish the device's
physical cause or guarantee a full HIGH match; hardware validation is required.

## Prior r3 failure and retained r4 recovery

The October 5 r3 log and matching NRO build ID
`4bb9eac9e2feab1005d8511d9ab37f683199c67d` identify HIGH, DXVK 3.1.1,
and a verified 32-bit no-alias process. At 91.569 seconds private FEX heap
allocation fails for 10485760 bytes/alignment 16. At 91.575 seconds an
unhandled native write exception parks the thread. The PC is FEX DLL RVA
`0x11dd0`, in the backing vector growth for `GuestToHostMap::BlockList`.
The pinned DLL disassembly shows the allocation returning zero, then a
write to zero plus the old 5-MiB vector length (`FAR=0x500000`).

This proves the immediate failure, not why the existing fragmented-page
fallback failed. r3 did not capture its failure stage or free heap at that
moment. Startup's used-memory figure includes the pre-reserved native heap
and cannot establish that all physical memory was exhausted at the freeze.

r4 preserves the ordinary malloc and fragmented-page recovery paths. If both
fail, private FEX containers may borrow only idle pages from the existing
64-MiB compiler arena. Small scratch/lookup requests gain the same last-resort
path. Compiler workspaces retain 8-MiB allocation granularity; pressure loans
use 4-KiB pages, preserve the original header/alignment/free contract, and
return their exact pages. No extra physical arena, pointer relocation, live
cache eviction, graphics/timing change or guest-memory alias is introduced.
The pool is bounded and cannot guarantee success at genuine exhaustion.

On this rare recovery path, Debug launch records the exact page-failure
stage plus heap/reserve usage. A final failure is synchronously retained in
crash.log as `FEX_HEAP_FAILED` before control returns to the frozen PE caller.
Normal launch still writes no diagnostics. Stage codes: 1 invalid size,
2 shared byte budget, 3 owner slots, 4 source allocation, 5 descriptor,
6 virtual range, 7 reservation, 8 kernel map (with its Result code).

The new ARM64 regression reproduces r3's 10-MiB failure with four modeled
causes and verifies r4 recovery while preserving an existing 5-MiB buffer
and live compiler workspaces. It also checks alignment, holes, real exhaustion
and teardown. These modeled causes are not claimed as the device's cause.
Host ASan/UBSan checks cover 256 small simultaneous loans and 4000 concurrent
ownership transfers. Hardware must still confirm that spare reserve pages
are available at the reported failure and that HIGH survives repeated events.

## Two launch paths

The normal PES13 tile keeps the existing graphical loading screen. It does
not start file diagnostics, the black debug view, profiling or sampling.
Saves, registry, preferences, functional caches and last played remain enabled.

Settings > Show debug launch exposes an optional fifth tile in the same NRO.
Selecting it draws a black startup console on the existing launcher framebuffer.
The launcher owns this view; there is no second debug thread or VI layer.
Its refresh interval is 200 ms during startup. Before the game takes the native
window, `fx_handoff()` stops and joins the launcher. Its framebuffer/artwork
are released and the startup flag is cleared. There is no in-game console to
hide, and Minus has no debug action. Game takeover may precede the PES menu;
errors after takeover remain in the file log.

The former persistent screen overlay and HEALTH polling are removed. This
supersedes r2's hold-Minus instructions, which did not work on the user's
paired Joy-Con/handheld. The failed hide behavior was not reproduced on hardware;
the disputed overlay path is no longer part of the build.

## Debug files and overhead

Only selection of Debug launch arms these files under `switch/pes13-fex`:

- `fex-runtime.log`: startup stages, bounded native/stdout messages and Wine
  errors/warnings, continuing after game takeover. One prior debug run is kept
  as `fex-runtime.previous.log`.
- `crash.log`: the existing bounded fatal writer for FEX STOP, native exception,
  nonzero guest exit, Rust/FEX allocation failure, abort and libnx fatal paths.
  One previous file is retained as `crash.previous.log`.

Routine capture callbacks use a fixed RAM ring/queue and try-lock/drop behavior.
They do not write to SD, allocate or wait for the file worker. The existing
maintenance thread flushes queued runtime text once per second, only when
there is data. Runtime output has a 64-KiB queue and 4-MiB per-run file limit;
dropped messages and the limit are marked. Failure to open/rotate or write a
log disables that file without stopping the game. A failed rotation does not
truncate the current evidence. A partial final line or messages from the last
second may be absent after forced termination.

Fatal capture is preallocated at explicit debug launch and retains the original
8-record bound, direct native FS flush, module/build identity and exception
registers. It is independent of periodic log flushing. Fatal paths use fixed
storage and do not wait on their local guard. FS IPC can still fail or block;
this is not a replacement for an OS crash dump. A header-only crash.log means
capture was armed, not that a crash occurred or that the game never froze.

Verbose per-operation tracing stays off. The build does not restore the previous
per-Vulkan-call observers, malloc observers, thread suspension/sampling, HEALTH
queries or transition.log. Loader channel tracing is requested during startup;
Wine errors/warnings remain available afterward. Debug file logging has CPU and
SD overhead even after its console closes. Use normal launch for FPS comparisons.
The runtime cannot control crash reports written independently by Atmosphere.

## One launch-time memory check

The process layout is read once during launcher bootstrap, before libnx's heap
and applet/HID/VI setup. Later preload/launcher guards reuse the cached result.
No game-loop memory-mode check or periodic health query is installed.
Only a recognized 32-bit address range with zero alias region is accepted;
failed/unknown queries, 32-bit with alias and other address ranges are rejected.
The supplied forwarder requests `address_space_type = 2`.

Loader-provided heaps are preserved. Without a loader override, compatible
launches retain the previous 256-MiB default. Incompatible layouts use a smaller
32-MiB rejection heap with fallback to 2 MiB, skip the fixed PES image reservation,
and return to the loader if that heap cannot be allocated. At launcher entry,
a text warning explains the NSP requirement and +/B returns to the loader.
The native runtime remains AArch64; the process address layout is not RAM clock
speed, and an NRO cannot change the memory mode of an already-running process.

This early guard is necessary because libnx heap allocation precedes `main()`;
putting the query exclusively in a Play-button handler would leave the original
pre-main failure gap. It performs no monitoring during gameplay.

Implementation references:

- [libnx initialization](https://github.com/switchbrew/libnx/blob/master/nx/source/runtime/init.c)
- [libnx kernel information types](https://github.com/switchbrew/libnx/blob/master/nx/include/switch/kernel/svc.h)
- [Atmosphere address-space layout](https://github.com/Atmosphere-NX/Atmosphere/blob/master/libraries/libmesosphere/source/kern_k_page_table_base.cpp)

## Build, validation and limits

Host ASan/UBSan checks cover the bounded capture queue, file rotation, storage
failure, idle writes, file cap, crash writer, address-space classification,
settings, preset/controller preservation and renderer transactions. Preview
images are fixtures produced by the real C UI renderer, not console photographs.

ARM64 execution tests cover the real linked libnx startup, cached gate, silent
stdio, log producers, public game-window takeover, bounded fatal capture and
memory recovery. The kernel, display IPC, thread scheduling and storage calls
are modeled. The normal path is exercised with forbidden filesystem calls;
late debug errors remain queued after the launcher handoff. The final ELF has
no debug overlay worker, HEALTH poller or transition-call observer. Tests do
not boot PES, certify device presentation, measure FPS or prove match stability.

The build/packager compare native libraries and unchanged recovery components
with `local/high-native-heap/build-report.json`. Four native FEX adapter files
are explicitly allowed to differ: horizon_jit.c, horizon_scratch_reserve.h,
horizon_scratch_pages.h and the new horizon_heap_pressure.h. The capacity,
Wine backing-store mapping protocol, thread-stack reserve and Rust shim ABI remain unchanged.
The additional Mesa CPU binding is separately recorded and hash-checked. Wine
pool-pressure changes and shared CPU owner changes are explicit. GPU/executable
allocation paths, game timing, renderer and presets remain unchanged. Historic patch-stage fields
such as transition_trace describe builder inputs; the final report specifies
`diagnostic_file_writes = "debug-launch-only"`,
`debug_console_scope = "launcher-startup-only"` and
`debug_gameplay_overlay = false`.

Build with `tools/build-fextendo-input-fix.py` and the existing pinned archive
and Wine tarball, adding `--transition-trace --scratch-reserve
--scratch-reserve-mib 64 --crash-log --live-freeze --page-store
--thread-stack-reserve --scratch-pages --rust-heap --production`.
`tools/package-fextendo-screen-debug.py` verifies source/binary hashes and all
required receipts before packaging an unused output directory. It creates no ZIP.
Only `switch/pes13-fex/pes13-fex.nro` is deployed; DLLs, assets and saves are not
included. The runtime lock and published release are not changed.
