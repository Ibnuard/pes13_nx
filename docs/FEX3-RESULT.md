# FEX3 reserve-fix: complete Switch stress-test PASS

## Native L1 device run: intro stalls, then executable memory is exhausted

The latest supplied `pes13-fex3-native-lookup-update` log is preserved at
`local/fex3/code-persistence/before/fex-runtime.log` (SHA-256
`62b320a69384b437c680471f03e4f8bb70cbf7db4920290859401c9bccbab9b0`).
It shows no `FindBlock` fault. The intro is already slow at 25–40 seconds:
Vulkan presents advance 348 -> 478 while audio underruns rise 7 -> 572.
This precedes the first large code-cache allocation failure.

At about 55 seconds, the attempted fresh 128/64/32/16 MiB RW/RX aliases fail
and FEX falls to 8 MiB, then repeated 4 MiB buffers. Around 75–80 seconds
even a 2 MiB alias fails (`0xce01`), followed by `[FEX3-CODE] STOP`, Wine
`c0000022` commit failures and parked threads. Presents stop at 1,256. The
terminal freeze is thus tied to executable memory/cache turnover; this alone
does not explain the earlier 1 FPS-like video playback.

The `early-128` candidate changes only the initial FEX code buffer request
from 64 to 128 MiB. A linked ARM64 model passes 17 code allocation/growth/
fallback/lifecycle cases, and the native L1, lookup, scratch, SMC, memory,
allocation and host ABI tests pass. All host/kernel services in those tests
are modeled. The candidate has **not yet been tested on Switch**.

The user-supplied logs confirm the complete original FEX3 stress workload on
Switch, using the reserve-fix build marker. This advances beyond the previous
run, which passed one worker wave then failed a 64 MiB reservation.

| Check | Device result |
| --- | --- |
| Native register/NEON/FP state roundtrip | PASS |
| Concurrent native exception frames | 64 roundtrips, 4 overlapping handlers, all slots released |
| Native/PE module index and unwind tables | PASS |
| Callback ABI, allocations, heap and physical counter | PASS |
| Original guest workload | 4 waves, 16 workers |
| Automatic SMC updates | 256 PASS |
| Handled guest access violations with context resume | 256 PASS |
| Math, TLS and normal worker exits | PASS in each wave |
| Runtime lifecycle | PASS, 16 exits and 15 reaped server threads |
| Process exit | `0x00000000` |

The final `parked after self-terminate; close from HOME` is the runtime's
normal successful exit behavior. The `c0000005` entries in bounded exception
breadcrumbs belong to the deliberate guest fault checks; the guest confirms
that every expected fault was handled. Neither log contains a FAIL/STOP,
out-of-address-space report or unhandled-status line in this run.

The native lifecycle counters finish at one running thread/object/connection,
four pipes and at most one pending thread/TEB/zombie, within the existing
verdict's bounds. These counters and this finite workload do not constitute
an exhaustive FEX heap-leak audit.

## Preserved evidence

Local copies, the machine-readable result and delivered build/package receipts
are in the ignored `local/fex3/hardware-pass/` directory.

- `fex-guest.log`: 757 bytes, SHA-256
  `7193b3f5ed7e8475777dc2bd7f3f01578f6014d51d38aa35585370546c586a9a`.
- `fex-runtime.log`: 26,603 bytes, SHA-256
  `220a7ce8ceb7482073daef98a1a52c6f1e5830a341e0c179223ce826250df578`.
- Delivered NRO SHA-256:
  `3cb793c74339ad20d592353d6a8183071d16f0bdc8f5e072699ff095ee96fc44`.
- Delivered update ZIP SHA-256:
  `219201d7657e5c3d2327de9f6b8be063b1a272ce5434273b8563ca6889fd1499`.

The logs identify the reserve-fix markers. Files on the physical Switch were
not independently hashed. The original package and its pre-test receipts
remain unchanged; this document records the subsequent hardware result.

## Subsequent PES run: heap address exhaustion

The next uploaded runtime log is `mode=PES13`, 35,470 bytes, SHA-256
`cc3d0a26ccf94af478af79d0a75cfbd27f12d2395dfbf61d63ea8e6c57cafd76`.
It initializes DXVK/Vulkan and reports the D3D9 device, then stops while a
new FEX thread heap requests 64 MiB: `STATUS_NO_MEMORY`. Wine's snapshot has
1098 MiB anonymous address reservations, 361 MiB committed, and a 2048 MiB
excluded system region. This establishes address-allocation failure, not
exhaustion of all physical RAM. The raw kernel-free ranges do not account
for every uncommitted Wine reservation.

The submitted guest log is still the 757-byte PASS above, with an earlier
timestamp; it is not evidence that the game completed. The PES failure and
build receipts are saved separately under `local/fex3/aligned-heap/before/`.
The successful hardware baseline remains intact.

The [aligned-heap candidate](FEX3-INTEGRATION.md#previous-candidate-exact-aligned-heap)
removes rpmalloc's padding reservations, reducing each 32 MiB span's address
request from 64 to 32 MiB. Its device result follows below.

## Aligned-heap PES run: surface created, another allocation stop

The next log is 37,997 bytes, SHA-256
`eaec7e700091ff4e85da9e1aa2efee0b60c2973f0c75bdd0d43b858297aa5891`,
preserved under `local/fex3/compact-heap/before/pes-runtime.log`. It carries the
v6 aligned-heap marker and progresses past the earlier failure: the Vulkan
surface is created at 1280x720, four DXVK compiler threads start, and the
audio DLLs load. No completed frame or successful audio playback is established.

It then reports 240 Wine views: anonymous 1301 MiB (587 MiB committed), images
119 MiB, and the 2048 MiB excluded system region. A 32 MiB aligned heap request
fails with `0xc0000017`. The explicit heap STOP traps at `0xff6c48a0`, and Wine
parks the thread with `0x80000003`. This explains why the window remains black
without the application closing. The remaining kernel-free ranges do not
establish that an aligned, Wine-usable 32 MiB hole exists.

The [compact-heap candidate](FEX3-INTEGRATION.md#previous-candidate-compact-heap)
reduces spans to 8 MiB, medium pages to 1 MiB and large pages to 8 MiB. Requests
over 2 MiB use direct allocation. Its subsequent device result follows.

## Compact-heap PES run: more workers, another address allocation failure

The new log is 41,164 bytes, SHA-256
`c2d6a02045e2eda8b156bcee11ed3ec3c1d13fb740f43ba9ac6c5b2f77e5d89c`,
saved as `local/fex3/compact-cache/before/pes-runtime.log` with the preceding
build/package receipts. It has the v7 heap marker and launches PES. DXVK and
audio modules initialize, and game worker creation reaches reported TID 100.
Many workers start at `0x4da0e3` in the PES executable. This is not just the
four DXVK compiler threads. The two `0x406d1388` exceptions are guest thread
naming notifications, not the logged fatal error.

The final error is `VirtualAlloc2 size=0x800000 type=0x102000`, returning
`0xc0000017`, followed by `STOP reserve failed`. Wine reports 361 views:
anonymous 1474 MiB (745 MiB committed), images 119 MiB and an excluded
2048 MiB native system region. Listed lookup views reserve 25 MiB each with
only 64-188 KiB committed. This establishes address allocation failure;
the kernel's raw free ranges can overlap uncommitted Wine reservations.

The [compact-cache candidate](FEX3-INTEGRATION.md#previous-candidate-compact-cache)
omits the index and backing for disabled L2 caches. The pinned default is
L2-off, so the unchanged L1 requires 1 MiB per thread instead of 25 MiB.
An explicit L2-on configuration retains the old complete layout. Local
binary pressure, lookup/invalidation, dynamic L1, heap, SMC and exception
tests pass. The NRO, ARM64 ntdll/WOW64 and original guest test are unchanged.
Its subsequent Switch runs are recorded below. PES menus, match stability,
input/audio playback and FEX game performance remain unverified.

## Compact-cache PES runs: compiler scratch and heap exhaustion

Both logs carry `[FEX3-LOOKUP] L2=off reserve=1 MiB/thread`. The input folder's
old `compact-heap-update` name does not identify the running DLL. The logs are
saved independently under `local/fex3/scratch-reuse/before/`:

- `pes-blackscreen.log`: 47,524 bytes, SHA-256
  `860d939b794f062f944164e638ee26e13d9e5deb1ffd2ceffc2ac7ddf6594fe8`.
- `pes-second-run.log`: 45,860 bytes, SHA-256
  `02e4c76f22b32404c977004898f254f6fce5e999e1b5ec96aeda25125e45d76b`.

The first reaches the D3D9 swapchain and game worker TID 140, then reports
470 Wine views: anonymous 1472 MiB (1083 MiB committed), images 119 MiB and
the excluded 2048 MiB native range. `VirtualAlloc` of 16 MiB returns
`0xc0000017`. With DLL base `0xfb5c0000`, fault PC `0xfb6bb200` is RVA
`0xfb200`, `FEXCore::IR::IREmitter::ResetWorkingList()+0x20`. The instruction
stores to the second half of the null IR buffer, matching fault address
`0x800010`. FEX's exception route stops at `smc-lock`; this is not evidence
that the black window is caused by intro video or a shader problem.

The second reaches a similar worker-creation phase, then reports 450 views:
anonymous 1421 MiB (1026 MiB committed), images 119 MiB and the excluded
native range. An aligned 8 MiB `VirtualAlloc2` request fails and the heap
explicitly stops. These establish address-allocation failures; raw kernel
free-range sizes do not establish guest-usable capacity, and TID 140 is a
thread identifier, not a count of 140 simultaneous threads.

Pinned source and the linked ARM64 module identify the IR buffer as 16 MiB
and decoder scratch as 8 MiB. The shared pool waits five seconds before
reclaiming disowned buffers. The [scratch-reuse candidate](FEX3-INTEGRATION.md#previous-candidate-compiler-scratch-reuse)
consumes suitable disowned buffers before allocating more, keeping sizes and
atomic ownership intact. It also stops failed allocation before publishing
a null buffer. Its subsequent on-device report follows.

## Scratch-reuse: stress reported PASS; second PES run stops at native startup

The user confirms `[FEX3-FAULT] PASS` and `[FEX3-GUEST] PASS all checks` with
scratch-reuse. This is a user-reported result; the guest log in the local
upload folder still has an older timestamp and is not treated as fresh proof.
The first PES run reportedly displayed a frame and then stalled at loading.
The supplied file is explicitly the **second** attempt, which showed no frame:
36,219 bytes, SHA-256
`32e06df0131d1e9b15be1e5ecd7016f60ad8cac13a436fe116ee9088e781714d`.
It is archived as `local/fex3/fd-routing/before/pes-second-run.log`, together
with the previous native ELF and package/build receipts.

Both scratch v1 and the 1 MiB lookup marker are present. DXVK initializes,
then the final line creates TID 44 for an mmdevapi entry point. TIDs 40 and 44
lack a WOW64 entry marker; no allocation failure, exception or exit is logged.
The log cannot establish the final program counter or prove audio is at fault.
The native startup path before that marker includes the server pipe handshake.

Source audit found all client descriptor transfers placed in one global FIFO
with tag zero. Native `init_first_thread`, `init_thread` and `new_thread`
ignored their explicit protocol descriptor fields and consumed queue order.
The local test executes the preceding ARM64 handler with interleaved sends:
the child requests original descriptors 101/103 but adopts 101/202, where 202
belongs to a parent's concurrent new-thread request. This proves a real
misrouting bug, consistent with the intermittent startup behavior, without
proving it is the sole cause of this particular device stall.

The [FD-routing candidate](FEX3-INTEGRATION.md#previous-candidate-native-startup-fd-routing)
matches the original descriptor under the queue mutex and broadcasts keyed
wakeups. It retains reverse-direction FIFO semantics and drains only the
matched duplicate of unsupported `alloc_file_handle` requests. FEX, PE Wine,
stress guest and renderer stay byte-identical; only the native NRO changes.
Local linked-ARM64 routing and native regression tests pass. The updated NRO
still requires hardware stress and repeated PES startup tests.

## FD-routing PES run: frame presented, executable JIT growth fails

The user reports two attempts that both show a loading frame and then stall.
One runtime log is available, 48,910 bytes, SHA-256
`38a4b1c9359362d0a456e19f105a3020d003429708036db03c9f1da2237f064e`.
It is preserved at `local/fex3/jit-growth/before/pes-loading.log`; this is not
two independent log captures. FD-routing v1, scratch reuse and 1 MiB lookup
markers are present. DXVK recreates the initial swapchain at 1280x720 and
presents 2, 3 and 4 return success. This corroborates the reported visible frame.

Executable allocations succeed for the 16 KiB dispatcher and shared code
buffers of 16 and 32 MiB. The next 64 MiB `jitCreate` returns `0xdc01`, after
which FEX logs `executable allocation failed`, traps with BRK, and Wine parks
the thread (`0x80000003`). The earlier Box64 lookup fault's address and status
are absent. The visible loading stall here is explained by this explicit stop.

The linked libnx implementation returns `0x559` for backing allocator failure;
`0xdc01` is kernel `InvalidMemoryRange`. It can follow a failed alias search
being passed as NULL to CodeMemory mapping. The old log does not identify
which mapping stage failed or establish total physical memory exhaustion.
The [libnx JIT implementation](https://github.com/switchbrew/libnx/blob/master/nx/source/kernel/jit.c)
and [Horizon-compatible kernel checks](https://github.com/Atmosphere-NX/Atmosphere/blob/master/libraries/libmesosphere/source/svc/kern_svc_code_memory.cpp)
document the allocation and range validation paths.

The [JIT-growth candidate](FEX3-INTEGRATION.md#current-candidate-executable-jit-growth-fallback)
adds native stage diagnostics and smaller fresh-buffer fallback, preserving
the normal shared-pointer lifetime of older executable code. Its device
startup and gameplay results remain pending.

The candidate builds successfully through WSL. Its delivered native ELF is
`d0178b473212e407f044296bd6740b2b4d2949875c361238e212f3052cd0c4a1`,
NRO is `00e452c31d8bafafa44dbdeebdd6d12f4d775a54eed3b409d93236bf0e69f5ba`,
and FEX DLL is `340f33f615e0c9fa9b4ef3b6c573472e37514997ab9bb7fcc3c3eabec2c44ca9`.
Thirteen linked-ARM64 growth tests and eleven native JIT cases pass, including
old-binary reproductions, actual-capacity bounds, thread/signal lifetime,
partial-map cleanup, and bounded oversized-block/validation failure. Existing
memory, lookup, scratch, SMC, FD-routing, exception, unwind and host-ABI tests
also pass on these binaries. Their exact hashes and modeled-service limitations
are recorded in `local/fex3/jit-growth/` test receipts. Physical Switch retesting
remains necessary.

## Startup-probe run: Vulkan presents, then no executable RW alias

The user closed the stalled run immediately and supplied a single runtime
log. Its immutable copy is `local/fex3/small-cache/before/fex-runtime.log`,
SHA-256 `56676565af241c9e68bdbbe54e59d6b1e062c1c5cbcc9006d4e932c681bd93c7d`.
The five-second heartbeat counts 143 Vulkan presents at 20 seconds and 308
at 25 seconds, so the process did reach its rendering path. The progress
sample at 20 seconds reports 1,448 MiB heap used and 462 MiB free, 66
threads and 1.56 active CPU cores. These counters do not establish remaining
usable contiguous alias space.

The decisive lines are three native failures at `stage=find-rw rc=0xdc01`,
for requested code cache sizes 64, 32 and 16 MiB. Both alias addresses are
zero; the failure occurs in the RW address search before a kernel mapping
call. FEX then logs `[FEX3-CODE] STOP executable cache allocation
bytes=0x0000000001000000`, traps, and Wine parks the failing thread with
`0x80000003`. The continued present counter does not mean that thread
recovered. This explains the observed loading stall in this run, without
proving whether the limiting factor is virtual-address fragmentation or a
different alias-search constraint on Switch.

The new [smaller-cache candidate](FEX3-INTEGRATION.md#current-candidate-smaller-executable-cache-fallback)
tries fresh 8, 4 and 2 MiB executable buffers after larger searches fail,
and enlarges the native handle table to 64 slots. Local modeled ARM64 tests
pass, including 64-to-2 MiB fallback and slot exhaustion. The NRO and FEX
DLL have both been rebuilt. An on-device PES run is required to determine
whether a smaller alias can be found and whether startup proceeds.

## Smaller-cache PES run: allocation survives, code cache repeatedly rolls over

The user reports that loading still stalls but looks further along. The
submitted 60,880-byte runtime log is preserved at
`local/fex3/early-cache/before/fex-runtime.log`, SHA-256
`6b29b4421a1f0e339e30fa21c34daabb67d8575e553bc876f487887db9a23344`.
Its enclosing `dist/pes13-fex3-jit-growth-update/` folder is stale as a build
label: the log itself contains fallback successes to 8 and 4 MiB, which were
introduced by the smaller-cache FEX DLL. The local copy of that folder's NRO
and DLL is older and cannot establish which NRO was on the SD card.

No executable-cache `STOP` or terminal exception appears. Vulkan presents
reach 280 at 25 seconds and 361 at 30 seconds, then advance only to 369 by
45 seconds. During the slowdown the log shows 35 fresh code-cache fallbacks:
28 to 8 MiB and seven to 4 MiB. The 35-second progress sample reports 64
threads and 2.80 active cores, with 1,510 MiB heap used and 401 MiB free.
The `reads` counter stays at 308 from the 25- to 35-second samples. The log
therefore shows CPU-heavy translation/cache turnover correlated with poor
forward progress; it does not prove the exact screen frame or game state.

The pinned Box64 allocator in `vendor/box64/src/custommem.c` (commit
`dae0917c47b4edd8956f314210417a20fd225c4b`) suballocates individual
dynablocks from 128 KiB initially and then 2 MiB chunks. `FreeDynarecMap`
frees a block within a chunk, and optional age-based purge targets unused
blocks. FEX instead maintains one active shared `CodeBuffer` with a separate
guest-to-host map; a full buffer starts a new generation and switches a
thread's lookup map. That is why simply lowering the fallback size can keep
the process alive but repeatedly invalidate useful compiled code.

The next [early-cache candidate](FEX3-INTEGRATION.md#previous-candidate-early-64-mib-executable-cache)
requests 64 MiB at first use, before DXVK and guest workers grow the memory
map. The normal smaller-size fallback stays in place. This is an experiment
to test whether the earlier contiguous address space can hold a larger live
working set; the device result is described below. A segmented persistent FEX cache
inspired by Box64 would require new lifetime and invalidation tests.

## Native-scratch PES run: black screen with rejected-suspend polling

The 57,474-byte log is preserved at
`local/fex3/suspend-backoff/before/fex-runtime.log`, SHA-256
`6b17c5a2a7342b68fc7425798cb0f50312b404d17b27f778bcbd2e3bdbce2e39`.
The user reports the same black screen after the Konami/rating splashes.
The log confirms `[FEX-HOST] ABI 2` and successful 16 MiB native compiler
scratch allocation. It contains no previous `FEX2-ALLOC FAIL`, heap `STOP`
or terminal JIT `STOP`. A 128 MiB executable-cache request at about 55 seconds
falls back successfully to 4 MiB, so that allocation warning is not by itself
a process exit.

Vulkan presents increase to 1,195 by 60 seconds, then stay at 1,195 at 65
and 70 seconds. PES reads remain 666 in the 55- and 65-second progress samples.
During the final ten-second interval, the Horizon server handles approximately
313,524 each of `dup_handle`, `close_handle`, `get_thread_info` and
`suspend_thread`: about 31,352 rejected-suspend cycles per second. These map
to Wine's ARM64 PE `RtlWow64SuspendThread` handle validation followed by
FEX's local callback to `NtSuspendThread`; Horizon rejects suspension of an
already-running thread with `STATUS_NOT_SUPPORTED`. CPU rises from 2.15 to
3.48 active cores while no new frames or reads appear. This loop also occurs
earlier when presents advance, so it is a strong CPU-overhead candidate but
not proof that it alone blocks the intro or menu.

The next update preserves the Wine/FEX suspend path and adds a 1 ms backoff
only after `STATUS_NOT_SUPPORTED`. Its linked ARM64 PE build, import audit,
unwind/heap tests and host wrapper contract pass. It still needs device A/B
evidence; no gameplay or FPS improvement has been established.

## Early-cache PES run: reaches splash, then memory failures

The user reports that PES now passes initial loading and shows the Konami and
rating splash screens, then stays black where the intro should appear. The
63,666-byte runtime log is preserved at
`local/fex3/native-scratch/before/fex-runtime.log` (SHA-256
`a4128cc38b668aa4162b30e47a87029d14f745bc062652a909532a8073ce8136`).
Its first FEX executable cache is 64 MiB. Vulkan presents rise from 30 at
20 seconds to 2,164 at 75 seconds, then stop by 80 seconds. This establishes
that the renderer was presenting for most of the transition, but not that the
video decoder succeeded.

At about 60 seconds a fixed Wine mapping replacement fails during a 60 KiB
unmap (`errno=22`). Four 60 KiB FEX heap commits then fail with NT status
`c0000022` and park their workers. At about 75 seconds Wine also fails a
16 MiB `VirtualAlloc` for FEX compiler scratch (`c0000017`); that worker
parks too. Those errors are sufficient to explain a stall and need to be
resolved before diagnosing intro playback itself. `mapping_slots=8192` is a
pool high-water mark with a dynamic fallback, not proof of a hard pool cap.

The native-scratch candidate routes only unguarded compiler scratch to the
native heap and pairs a new ABI-2 FEX DLL with its NRO. The NRO adds a bounded
`[FEX3-HMAP]` kernel-result trace for the separate unmap failure. Local linked
ARM64 tests cover the ABI boundary, 16 MiB scratch ownership/reuse and prior
JIT/memory behavior. The Switch has not tested this candidate yet; the unmap
failure might still prevent intro/menu progress even if scratch succeeds.

## Suspend-backoff PES run: intro appears, then L1 commit fails

The user reports that the intro is now visible but very choppy before freezing.
The supplied 60,859-byte log is preserved at
`local/fex3/native-lookup/before/fex-runtime.log`, SHA-256
`ef17d8c116c92ffd46e27c1bef325a81600c89b6d05c7e343e6491bdc4eb8a8e`.
Although its upload directory still says early-cache, ABI 2/native scratch and
the reduced suspend-request rate are consistent with the latest installation.
Suspends fall from approximately 313,524 per ten seconds in the previous log
to 18,195 in one late interval. These intervals are not matched benchmarks,
but the previous sustained busy loop is much less active. After the terminal
fault, process CPU drops to about 0.24-0.29 active cores.

Vulkan presents reach 965 at 55 seconds, 1,266 at 60 seconds, and 1,452 at
65 seconds. Between the 65- and 70-second heartbeats, Wine rejects a 20 KiB
commit at `0xfeb55000` with `c0000022`. The ensuing read fault is at
`0xfeb55108`, PC `0xfedd7de0`, LR `0xfee7ebac`. The shipped FEX DLL's base is
`0xfedc0000`; its COFF symbols resolve these addresses to
`LookupCache::FindBlock+0x20` and `Arm64JITCore::ExitFunctionLink+0x7c`.
The register dump gives L1 base `0xfeac0000` and guest address `0x01219510`:
the masked entry offset `0x9510 * 16`, plus its guest-tag field at +8, resolves
exactly to the faulting address. Thread 4 is parked with `c0000005`; presents
then stay at 1,534 through 90 seconds.

This explains the terminal freeze as a native translator lookup-memory fault.
It does not determine why Horizon/Wine rejected that commit or whether every
preceding video stutter has the same cause. Audio underruns also rise before
the crash. Several new executable caches fall back to 8/4 MiB around 60-65
seconds, without a terminal code-allocation STOP. Repeated cache generations
remain a separate translation-overhead concern.

Comparison with the pinned Box64 source (`dae0917c47b4edd8956f314210417a20fd225c4b`,
`src/custommem.c`, `create_jmptbl`) shows native allocation and initialization
of jump-table entries before atomic publication. FEX's L1 instead relied on
Wine lazy commits, including after invalidation. The
[native-lookup candidate](FEX3-INTEGRATION.md#current-candidate-resident-native-l1-lookup)
uses the existing ABI-2 native allocation callbacks for the L2-off L1 and
clears entries without decommit. It preserves capacity, address masks and
the optional L2-on path. Fully resident tables trade more up-front physical
memory for removal of L1 commit faults: up to 1 MiB per live FEX thread.

The DLL builds through WSL, SHA-256
`226d207d075fc967f24074e04f72bc97ab181a9bff8a8271c937c3939b511b82`.
Its linked-ARM64 regression injects the observed `c0000022` failure into the
old lazy-commit path and reproduces the protected read. The new DLL handles
the same high-offset lookup, dirty host allocations, collisions, 16 complete
clear/refill cycles and release with zero NT commits. Existing tests also
pass: 296 constructors/destructors, 32 concurrent model caches, 2,464 lookups,
120 invalidations, 16 dynamic-size transitions, heap allocation, compiler
scratch ownership, SMC, executable-cache lifetime, ABI, and exception unwind.
These model NT/kernel services; on-device intro stability and FPS remain
unverified. Receipts are under `local/fex3/native-lookup/` and included in
the complete package manifest. Native-only FD-routing and JIT receipts are
reused against the identical native ELF hash.

The update includes the new FEX DLL and the unchanged suspend-backoff ARM64
ntdll. The existing ABI-2 NRO, configuration and user data are excluded from
the update. The rollback restores the previous FEX DLL and retains backoff.

## Early-128 PES run: menu reached, team selection exhausts memory

The user reports the furthest FEX progress so far: intro and menu appear,
then Exhibition -> controller selection -> team selection stops while music
continues. The input is preserved as `local/fex3/team-memory/before/fex-runtime.log`,
SHA-256 `046effb55464f126d6eba877c5fd8804185b33c0b840b60061a302a14292003e`.
The log confirms an initial 134,217,728-byte FEX executable buffer. It has
neither the previous code-allocation STOP nor the L1 `FindBlock` failure.

At 120 seconds Vulkan has presented 3,056 frames. Near the end Wine rejects
repeated 16,448 KiB reservations below 4 GiB. Its VA snapshot contains 504
views, 1,156 MiB of anonymous reservations (772 MiB committed), 119 MiB of
images and a 2,048 MiB native-system exclusion. The raw kernel's largest free
hole overlaps that exclusion; it cannot be treated as freely allocatable
guest VA. The 115-second native heap snapshot reports approximately 1,749 MiB
used and 162 MiB free, so this is not proof that all physical RAM is exhausted.

Vulkan allocation requests for 128, 64, 32 and 16 MiB return `-1`
(`VK_ERROR_OUT_OF_HOST_MEMORY`). DXVK ultimately cannot allocate a 196,608-byte
resource at 65,536-byte alignment. It reports its 1,536 MiB heap with 293 MiB
allocated, 271 MiB used, 273 MiB reserved and a 348 MiB budget. Immediately
afterward, guest PC `0xfb20fa4f` reads `0x6c`; Wine logs an unhandled fault and
thread 4 exits with `c0000005`. Thirty-three threads remain. This sequence
supports an allocation-related terminal failure; low GPU utilization or
continuing audio would not establish a purely CPU-performance stall.

The pinned FEX Windows adapter commits a 4 MiB CALL/RET prediction cache for
each emulated thread. The compact-callret candidate reduces only that cache
to 256 KiB. Its paired-address format, guest program stack, both guards,
recentring and invalidation remain intact. At 34 live stacks the theoretical
memory/VA saving is 127.5 MiB. It also rejects failed reserve/commit operations
before publishing pointers and releases the reservation on commit failure.
The early-128 JIT setting remains unchanged.

The DLL builds via WSL, SHA-256
`235cbce7a7221876152374cf2533ebe8dd11a08d933e3493d57c04d6e66ad3bc`.
The linked allocation model confirms 136 -> 8.5 MiB committed across 34
simultaneous stacks and leak-free non-LIFO destruction. ARM64 paired-access
stress performs 40,000 pushes and 14,000 pops, triggers lower/upper guards
9/1 times and resumes after the actual linked recovery routine. Tests also
exercise exact boundary classification, unrelated faults, old invalid OOM
publication, and new reserve/commit failure cleanup. This models NT services,
not full Horizon exception delivery. JIT, lookup, scratch, SMC, ABI, memory,
thread-exit and Wine unwind regressions also pass. Receipts are under
`local/fex3/compact-callret/`. The candidate has not run on Switch yet.

Performance is not uniform in the supplied run: successful Vulkan presents
rise from 1,644 to 2,223 during seconds 70-80 (about 58/s in that interval),
then much more slowly later. This is not a measured gameplay FPS result.
The hot syscall `0x31` resolves to `NtQueryPerformanceCounter` in the pinned
Wine syscall table; one interval records about 2.65 million calls per ten
seconds. That is a remaining CPU-overhead lead, not evidence that removing
or weakening the game's timing semantics would be correct. First validate
team loading after the concrete memory reduction, then profile a successful
match separately.
