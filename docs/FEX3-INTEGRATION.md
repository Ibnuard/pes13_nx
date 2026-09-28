# FEX3: concurrent faults and PES integration

The current candidate is documented in [FEX3-SELF-SUSPEND.md](FEX3-SELF-SUSPEND.md):
implement synchronous self-suspension after `team-sync` recorded a large stream
of rejected self requests and regressed to an intro freeze. It restores the
earlier Fastest configuration and retains the faster 2D work. The tester now
reports reaching a match, visually around 30 FPS with a few remaining bugs;
see the [preserved checkpoint](FEX3-CHECKPOINT.md). The history below
records earlier bring-up results, not validation of the current candidate.

FEX2 passed its original x86 smoke test on Switch, including explicit code
cache flushing. The first FEX3 test failed on automatic code modification:
`worker result=0x00000010`, followed by `FAIL worker workload`. This run does
not establish that the guest access-violation checks pass. The earlier verbal report of
both FEX3 checkpoints passing was corrected by this log.

The subsequent SMC-fix device run passed the native concurrent-fault checkpoint:
`64 roundtrips; 4 overlapping handlers; all slots released`. Its guest test
timed out in the first worker wave. Runtime logs show failed allocations and
eventual heap exhaustion; neither full guest SMC nor guest exception delivery
has passed on Switch.

The memory-fix device run has no logged allocation failures. All four workers
reach `phase=6`, `round=0`, then time out. Reaching that phase means each worker
accepted its first automatic SMC update, but it does not establish all-round
SMC correctness or successful guest exception delivery. Native concurrent
faults still pass.

The guest-fault-trace device run narrows the failure further. All four guest
handler counts, including the global count incremented before TLS, remain zero.
FEX reconstructs the expected guest EIP/ESP, calls `NtRaiseException`, and
native Wine continues to ARM64 PE `KiUserExceptionDispatcher`. The second
FEX callback with a native `EntryContext` PC is the normal
`Wow64PrepareForException` call, not evidence of another hardware crash.

The unwind-fix device run now reports **one complete worker wave PASS**:
four workers complete 64 automatic SMC updates and 64 strict handled guest
access violations, with math/TLS checks and normal exits. It then stops while
creating the second wave: a 64 MiB heap reservation fails. The complete
four-wave test has not passed yet.

**The previous package is `pes13-fex3-reserve-fix`. Its complete stress test
has now [passed on Switch](FEX3-RESULT.md).** The new logs show all four waves,
16 workers, 256 automatic SMC updates, 256 handled guest faults, native fault
and lifecycle PASS, and process exit code 0. This supersedes the earlier
single-wave result above.
It changes the NRO's address-conflict recovery and self-thread object query.
The ARM64 ntdll/WOW64/FEX DLLs and original x86 stress executable remain
byte-identical to the unwind-fix package. Memory/SMC repairs and bounded
diagnostics remain in place.
This does not establish that PES boots, completes a match or runs faster than
Box64. The FEX2 hardware-tested package is preserved separately.

## Current candidate: compact per-thread CALL/RET prediction cache

The early-128 device run reaches the PES menu. When the user enters
Exhibition -> controller selection -> team selection, Wine fails repeated
16,448 KiB guest-VA reservations and Vulkan allocations fail down to 16 MiB.
The final DXVK allocation failure is followed by a guest read at `0x6c` and
main-thread exit `c0000005`. Other threads remain alive, consistent with the
reported music continuing. This is still a runtime failure to fix before
using that transition as a performance benchmark. Details are recorded in
[the device result](FEX3-RESULT.md#early-128-pes-run-menu-reached-team-selection-exhausts-memory).

`pes13-fex3-compact-callret` keeps the early 128 MiB executable buffer and
resident native L1. It changes FEX's per-thread CALL/RET **prediction cache**
from 4 MiB to 256 KiB. This cache stores guest/host return-address pairs; it
is not the Windows program stack. Both inaccessible guard pages, recentering
on overflow/underflow, and code-invalidation clearing remain in place.
At 34 live threads the committed prediction caches total 8.5 MiB instead of
136 MiB, saving 127.5 MiB plus the same amount of guest address space.
This is the before/after allocation-model result, not a measured Switch heap
reduction or a guarantee that the next graphics allocation will succeed.
Reserve/commit failures now stop explicitly before publishing invalid state;
a failed commit also releases its reservation.

The WSL-built ARM64 DLL passes linked binary tests for initialization, both
guard boundaries, resumed paired accesses, 34 concurrent stack lifecycles,
out-of-memory cleanup, JIT cache growth, lookup, scratch reuse, SMC, ABI,
thread-exit gating and Wine exception unwind. NT/kernel services are modeled.
Smaller prediction capacity can cause more guard recovery for unusually deep
or unbalanced guest call sequences; hardware PES behavior remains unverified.

Close the app through HOME -> X, then extract
`dist/pes13-fex3-compact-callret-update.zip` at the SD root. Its only installed
payload is `switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll`.
The existing ABI-2 NRO, ARM64 ntdll and configuration remain in use. Leave
`run_guest_tests=0` to test PES. The startup marker is:

```text
[FEX3-CALLRET] v1 prediction stack=256 KiB/thread; guard recovery retained
```

Test the same Exhibition/controller/team-selection sequence, then enter a
match if it succeeds. Save `fex-runtime.log` before relaunching, including
the final lines if the picture stops. The accompanying
`pes13-fex3-compact-callret-rollback.zip` restores the exact early-128 DLL
that reached the menu. No FPS improvement or successful match is claimed yet.

## Previous experiment: reserve 128 MiB of FEX code during boot

The device log from `pes13-fex3-native-lookup-update` confirms the native L1
fix: the earlier `FindBlock` access violation is gone. The video still appears
very slowly, and the log shows two distinct phases. Vulkan presents increase
only from 348 at 25 seconds to 478 at 40 seconds, while audio underruns rise
from 7 to 572. This occurs **before** executable-cache turnover, so the new
code reserve is not a proven fix for the initial choppy playback.

At about 55 seconds FEX fills its initial 64 MiB code buffer. A fresh 128 MiB
RW/RX alias cannot be found; nor can 64, 32 or 16 MiB. FEX falls back to 8 MiB
and then repeated 4 MiB generations. At 75–80 seconds even 2 MiB fails,
`[FEX3-CODE] STOP executable cache allocation` appears, Wine commits fail with
`c0000022`, and several threads park. Vulkan presents remain at 1,256. This
accounts for the terminal freeze, but not necessarily for the earlier low FPS.

The working Box64 path uses retained code arenas: it starts at 16 MiB and adds
arenas as needed, keeping prior translated code addressable. Its earlier PES log
records 16 + 32 + 8 MiB arenas and 3,492 frames by 60 seconds. FEX instead
switches a thread to a fresh cache and clears its lookup when a buffer fills.
The `pes13-fex3-early-128` experiment requests 128 MiB for the **first** FEX
buffer, while the Switch address space is still open. If that request fails,
the existing 64/32/16/8/4/2 MiB fallback remains. This may defer the terminal
cache churn and let the intro continue; it does not change the video decoder or
claim Box64-equivalent execution speed. It can also reserve 64 MiB more physical
memory on a successful 128 MiB boot, so the result needs a device test.

For the existing ABI-2 FEX installation, close through HOME -> X, then extract
`dist/pes13-fex3-early-128-update.zip` at the SD root. Only
`switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll` changes; keep the
NRO, ntdll, configuration, game and profile. Leave `run_guest_tests=0` for PES.
The first large FEX executable allocation should say `size=134217728`; if it instead
says 67108864, the early request fell back. Save `fex-runtime.log` before the
next launch. Compare video playback, whether presents advance beyond 1,256,
and whether any `[FEX3-CODE] STOP` remains. The paired rollback archive restores
the previous native-L1 DLL. The subsequent device run reached the menu with
the 128 MiB allocation; team-selection failure is covered by the current
candidate above.

## Previous candidate: resident native L1 lookup

The suspend-backoff device run now displays the intro, according to the user,
but playback stutters and then freezes. Its log shows a concrete terminal
failure: committing 20 KiB for FEX's L1 lookup returns `c0000022`, followed by
an access violation in `LookupCache::FindBlock`. Thread 4 is parked and Vulkan
presents stop at 1,534. This is a translator-memory failure; the log does not
establish a broken video decoder. See [the recorded result](FEX3-RESULT.md#suspend-backoff-pes-run-intro-appears-then-l1-commit-fails).

Box64's pinned `create_jmptbl` allocates and initializes native jump-table
memory before publishing it. The new `pes13-fex3-native-lookup` adapts that
ownership principle to FEX: with the existing `DisableL2Cache=true` setting,
the 1 MiB L1 uses the ABI-2 native heap callback and is zeroed before dispatch.
Invalidation, growth and shrink clear entries without Wine decommit; destruction
frees the native allocation. The optional L2-on path retains its existing lazy
VM behavior. Guest masks, lookup capacity and generated-code lifetime stay the
same. The tradeoff is up to 1 MiB resident native memory per live FEX thread,
rather than a partially committed 1 MiB Wine reservation.

Linked ARM64 tests reproduce the old protected lookup read with an injected
`c0000022` commit failure. The new DLL handles the same address, collisions,
invalidation/refill and release without any NT commit. Existing lookup tests
cover 2,464 lookups, 120 invalidations and 16 size transitions; the broader
heap, SMC, code-growth, ABI and exception tests also pass. NT/kernel services
are modeled, so these results do not prove a fix on Switch. Small executable
cache generations still recur in the log and may continue to cause stutter.

For the current ABI-2 installation, close via HOME -> X, then extract
`dist/pes13-fex3-native-lookup-update.zip` at the SD root. Replace the included
`switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll` and `ntdll.dll`.
The ntdll retains the rejected-suspend backoff. Keep the existing NRO,
forwarder, configuration, game and profile; leave `run_guest_tests=0` for PES.
The startup marker is:

```text
[FEX3-LOOKUP] L2=off native=1 MiB/thread; no lazy commits
```

Test two separate launches, saving `fex-runtime.log` before each relaunch.
Record whether intro and menu appear, and whether presents keep advancing.
The rollback archive `dist/pes13-fex3-native-lookup-rollback.zip` restores the
previous FEX DLL while retaining suspend backoff. For a new installation or an
older NRO without ABI 2, use the full `dist/pes13-fex3-native-lookup.zip` and
follow the setup instructions below.

## Previous candidate: rejected-suspend backoff

The device run with native compiler scratch again reaches the splash screens,
then stays black. Its ABI 2 and native-scratch markers confirm the matched NRO
and FEX DLL were installed. The earlier 16 MiB scratch failure is absent.
Vulkan presents reach 1,195 by 60 seconds and remain there at 65/70 seconds;
PES data reads likewise stop increasing. The executable-cache fallback at
about 55 seconds succeeds with 4 MiB buffers and does not report a terminal
`STOP`. Meanwhile Wine repeats roughly 31,000 duplicate/query/close/suspend
requests per second and CPU load rises to 3.48 active cores. This polling was
also present while frames advanced, so it is a plausible bottleneck rather
than a proven sole cause of the black screen. The intro decoder remains
unverified.

`pes13-fex3-suspend-backoff` changes only ARM64 PE `ntdll.dll`. When FEX's
local suspend callback returns `STATUS_NOT_SUPPORTED` for a running thread,
the caller sleeps for 1 ms and receives the original status. Successful
suspensions, other errors and suspend counts are unchanged. The CPU backend,
NRO, FEX DLL, DXVK and game files are unchanged. This experiment tests whether
reducing the rejected-suspend loop restores forward progress. It is not a
running-thread suspension implementation or a measured FPS improvement.

For the current native-scratch installation, close via HOME -> X and extract
`dist/pes13-fex3-suspend-backoff-update.zip` at the SD root. It replaces only
`switch/pes13-fex/drive_c/windows/system32/ntdll.dll`; keep the existing
ABI 2 NRO and FEX DLL. Save `fex-runtime.log` after each of two separate PES
launches before the next overwrites it. Check whether the intro/menu appears,
then compare `[SERVER] suspend_thread` counts per 10-second interval and
`[FEX3-BOOT] vk_presents` after the splash. If startup regresses, extract
`dist/pes13-fex3-suspend-backoff-rollback.zip` to restore the previous PE
ntdll. The complete package is `dist/pes13-fex3-suspend-backoff.zip`.

## Previous candidate: native FEX compiler scratch

The early-cache Switch run now gets past initial loading and the Konami/rating
splash screens. It then stays black instead of reaching the intro/menu. The
runtime still submits Vulkan frames during that transition; the first confirmed
terminal problems in the log are four 60 KiB Wine heap commit failures near
60 seconds and a 16 MiB FEX compiler scratch allocation failure near 75 seconds.
The latter parks a worker, after which Vulkan presents stop advancing. The log
does not establish whether the intro video decoder itself works.

The 16 MiB workspace needs native compiler memory, not a Windows guest address.
`pes13-fex3-native-scratch` moves only FEX's unguarded compiler scratch to the
Horizon host heap. Guarded temporary JIT buffers, executable code mappings,
guest-visible allocations, and the early 64 MiB code-cache policy stay as
before. The host ABI is now version 2; the NRO and `libwow64fex.dll` must be
updated together. The NRO also logs the underlying Horizon result and source
address for up to 16 failed code-memory unmaps as `[FEX3-HMAP]`. That separate
60 KiB failure has not been fixed yet.

For an existing FEX3 installation, close it with HOME -> X, then extract
`dist/pes13-fex3-native-scratch-update.zip` at the SD root. Replace the two
executables under `switch/pes13-fex/`; retain the existing `configuration.ini`,
game, profile and saves. Keep `run_guest_tests=0` for PES. Save
`switch/pes13-fex/fex-runtime.log` after each launch before starting it again.
Look for `[FEX-HOST] ABI 2`, `[FEX3-SCRATCH] native size=16777216`,
`[FEX3-HMAP]`, and whether Vulkan presents still advance after the splash.
This is an on-device experiment, not a confirmed intro fix or FPS gain.

## Previous candidate: early 64 MiB executable cache

The first PES run with the smaller-cache fallback no longer reaches an
allocation `STOP`. DXVK presents rise to 361 by 30 seconds, but only 369 by
45 seconds while the CPU approaches three busy cores. The log shows 35
successful **new** cache fallbacks, mostly to 8 MiB and some to 4 MiB. FEX
allocates another buffer when the current one fills; the new buffer has a new
guest-to-host map, and each thread switches to it by clearing its local lookup
cache. Repeating this at 8 MiB can make PES translate its working set again.

The pinned Box64 implementation uses a different strategy: it suballocates
native code per translated block from a list of 128 KiB/2 MiB chunks, frees
individual blocks and can purge old blocks under pressure. This avoids a
single active shared buffer being replaced whenever it fills. FEX's code
references, lookup maps and cross-thread invalidation need a separate design
to adopt that strategy safely. We are not copying Box64 flags into FEX.

`pes13-fex3-early-cache` tests a smaller targeted step: ask FEX for a 64 MiB
first code buffer before PES/DXVK fragment the process address space. The
existing fresh-buffer fallback remains, so initial 32/16/8/4/2 MiB buffers
are still possible if 64 MiB is unavailable. This changes the FEX DLL; the
package also includes the matching current NRO to avoid mixed versions.
Local linked-ARM64 tests check the actual initial request, early fallback and
that 32 MiB of generated code fits without a cache rollover. This does not
establish that a 64 MiB RW/RX pair is available on the Switch, nor that PES
will boot or run faster. Keep the working Box64 prefix separate.

Use `dist/pes13-fex3-early-cache-update.zip` on an existing FEX3 prefix. Close
the app via HOME -> X, extract `switch/` to the SD root and replace the NRO
and `libwow64fex.dll` together. Preserve `configuration.ini`, PES files and
profile. In PES mode (`run_guest_tests=0`), save `fex-runtime.log` after each
run and before relaunch, then compare the first `[FEX-JIT] slot=... size=...`
line for a shared buffer with the previous 16 MiB start. The complete
package is `dist/pes13-fex3-early-cache.zip`.

## Previous candidate: smaller executable cache fallback

The startup-probe log resolves the new loading stall. PES reached DXVK and
presented hundreds of frames. FEX later needed another executable code cache,
but native `virtmemFindCodeMemory` found no RW alias for 64, 32 or 16 MiB.
Each attempt stopped at `stage=find-rw rc=0xdc01`; FEX then logged
`[FEX3-CODE] STOP` and the native exception handler parked that thread. This
is an address-space allocation failure, not proof of exhausted physical RAM.

`pes13-fex3-small-cache` extends the existing **fresh-buffer** fallback down
to 8, 4 and 2 MiB. It also expands the native code-memory handle table from
8 to 64 slots, because smaller buffers can coexist with older live code. The
FEX DLL and NRO both change. Existing executable buffers retain their normal
thread and signal ownership; this change does not reset compiled code. Local
linked ARM64 tests cover fallback, capacity, old-code lifetime, slot exhaustion,
alias bounds and cleanup. Kernel/NT services are modeled, and whether a 2 MiB
alias exists in the real PES run remains unverified.

For an existing FEX3 installation, use
`dist/pes13-fex3-small-cache-update.zip`. Extract `switch/` to the SD root,
replacing **both** `switch/pes13-fex/pes13-fex.nro` and
`switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll`. Keep the existing
`configuration.ini`, game and profile. The complete package is
`dist/pes13-fex3-small-cache.zip`. With `run_guest_tests=0`, try two separate
PES launches. Save each `fex-runtime.log` before starting the next run; it is
overwritten at startup. A useful result records whether a `[FEX3-CODE]
fallback requested=... actual=...` line appears, whether `STOP` recurs, and
whether the PES menu appears. No FPS improvement is claimed yet.

## Previous candidate: bounded startup probe

The preceding JIT-growth run stopped before its first logged Vulkan present,
after an unidentified popup activated. The user waited under two minutes. The
probe added five-second boot/present summaries, ten-second progress summaries
and bounded popup identity logging. Its next run supplied the decisive JIT
alias failure above; the probe itself did not change the FEX DLL.

## Previous candidate: executable JIT growth fallback

The user reports that both FD-routing attempts now display a PES loading frame.
Only one runtime file is available: it reports successful 1280x720 presents,
then `jitCreate size=67108864 rc=0xdc01`, followed by an explicit FEX allocation
trap and a parked thread. This is executable JIT allocation failure, separate
from the earlier Box64 guest lookup fault. The result is a kernel invalid-range
error, not evidence that all physical RAM has been exhausted.

FEX normally grows the shared code buffer from 16 to 32, 64 and at most 128 MiB.
Each Horizon CodeMemory object needs separate RW and RX address ranges. The
old adapter treated every failed growth attempt as fatal. This candidate tries
smaller **new** buffers down to 16 MiB when the requested size is unavailable,
and records the actual allocation capacity for all bounds. Existing buffers
remain owned by their threads and signal handlers until normal reference
release. No live translated code is reset or forcibly reclaimed. An explicit
size check prevents an oversized compiled block from causing endless rollover.
The optional disk-cache validation path also stops explicitly if its cache
cannot grow; normal successful growth remains enabled.

The native allocator checks alias-search failure before issuing a mapping
syscall and reports the failing allocation stage. Partial allocations are
cleaned up; unconfirmed cleanup is never returned to the allocator as free.
The host ABI, PE Wine dependencies, renderer and game/profile files are retained.

Local tests execute the delivered ARM64 routines: 13 code-growth cases cover
fallback, capacity, retained thread/signal references and bounded failure;
11 native JIT cases cover mapping failures, cleanup, alias bounds and slot
exhaustion. The old native binary reproduces `0xdc01` when a failed address
search is passed to the kernel. Heap, scratch, lookup, SMC, native exception,
unwind, descriptor-routing and callback-ABI regressions pass. Kernel/NT services
are modeled; these results do not establish Switch boot or performance.

Use `dist/pes13-fex3-jit-growth-update.zip` for the existing FEX3 install, or
`dist/pes13-fex3-jit-growth.zip` for the full dependencies. Close through HOME,
copy `switch/` to the SD root and replace all six payload files. The forwarder
path stays `switch/pes13-fex/pes13-fex.nro`. The default configuration runs
`run_guest_tests=1`; after both native and guest checks PASS, close and change
it to `0` for PES. Save each run's log before reopening. This candidate has
not yet been tested on the physical Switch and does not establish game FPS.

## Previous candidate: native startup FD routing

The user reports complete native/guest stress PASS with scratch-reuse. Its
first PES attempt displayed a loading frame; the submitted second-run log
stops before a frame, after thread creation for TID 44. It confirms scratch
v1 and the 1 MiB lookup mode, with no logged allocation STOP or exception.
TIDs 40 and 44 have no WOW64 entry marker. That marker precedes FEX thread
initialization, so this evidence directs investigation to native startup.
It does not prove the last logged audio component caused the stall.

Native Horizon descriptor transfer used a single client-to-server FIFO.
`init_thread` consumed the next two entries regardless of the original
`reply_fd` and `wait_fd` explicitly carried in its request. `new_thread`
similarly ignored `request_fd`. Parent creation and child startup can
interleave, handing a server thread someone else's pipe and leaving a client
waiting on a pipe that will not receive its reply.

This NRO records the **original native descriptor number before duplication**
and consumes the entry named by the request. The one native process shares a
descriptor namespace; startup keeps originals open until synchronous request
completion. Matching and removal run under the queue mutex, with broadcast
wakeups because different waiters may want different descriptors. Head,
middle and tail removal preserve the queue. Server-to-client transfers retain
their separate FIFO/Windows-handle semantics. Unsupported `alloc_file_handle`
still returns `STATUS_NOT_IMPLEMENTED`, but now closes only its own transferred
duplicate instead of leaving an orphan that could match a reused fd number.

The FEX DLL is byte-identical to scratch-reuse; compiler/lookup/heap fixes
remain. ARM64 ntdll/WOW64, x86 stress executable, renderer, game and profile
are unchanged. Native context, exception, reservation, cleanup and unwind
regression checks pass. Local FD tests reproduce pipe misrouting in the old
ARM64 runtime and verify identity matching in the new runtime. Descriptors,
pthread waits and deterministic interleavings are modeled; this is not a
Switch launch or proof that every PES startup issue has been solved.

```text
[FEX3-FD] v1 startup descriptors matched by original fd; keyed wakeups
```

Use `dist/pes13-fex3-fd-routing-update.zip` for the existing FEX3 install or
`dist/pes13-fex3-fd-routing.zip` for all dependencies. Close through HOME, copy
`switch/` to the SD root and replace all six files, including the updated NRO.
The forwarder path stays `switch/pes13-fex/pes13-fex.nro`. Run the default
`run_guest_tests=1`; after complete PASS, close and set it to `0` for PES.
Test two separate PES launches and save `fex-runtime.log` from each before
opening again: the next launch replaces that file. On-device results for
this candidate remain pending.

## Previous candidate: compiler scratch reuse

Two compact-cache PES runs confirm the 1 MiB default lookup marker but still
run out of guest address space. The blackscreen run fails a 16 MiB ordinary
RW allocation and faults in `IREmitter::ResetWorkingList` at `nullptr +
8 MiB + 0x10`. This is a compiler IR buffer, not the executable JIT cache.
The second run instead stops on an 8 MiB rpmalloc reservation. Both logs and
their preceding module/package receipts are preserved under
`local/fex3/scratch-reuse/before/`; see [FEX3-RESULT.md](FEX3-RESULT.md).

The shared compiler pools retain recently disowned buffers for five seconds.
IR uses 16 MiB and decoding uses 8 MiB per buffer. Many threads compiling in
that interval can retain those buffers even after they finish using them.
The candidate first uses the existing expired/unclaimed pool paths. Before
allocating another buffer, it can take a sufficiently large **DISOWNED** buffer
by atomically changing its old client's flag to **FREE** under the pool mutex.
A concurrent reowner or unclaimer that changes the flag first wins; the
candidate cannot take an **OWNED** buffer. It reuses the existing list node,
so this transfer does not itself allocate from the exhausted heap.

The original sizes, guard pages, compiler instruction limits and generated
code remain intact. The policy also applies to temporary backend compilation
buffers through the shared pool implementation; executable code buffers use
a different allocator. A failed allocation now stops explicitly before a null
pointer enters the pool. Guarded allocation skips page protection on failure.
This reduces idle retention, not the memory required by simultaneous active
compilers, and cannot guarantee that PES has no further allocation failures.

```text
[FEX3-SCRATCH] v1 reuse disowned compiler buffers before growth; capacities unchanged
```

Linked ARM64 tests reproduce the preceding DLL publishing a null buffer
after 13 sequential recent clients reserve 208 MiB in a bounded model.
The candidate serves 32 sequential clients using one 16 MiB buffer in that
same model. Twelve waves of four simultaneously owned clients retain four
buffers at both 8 MiB and 16 MiB capacities, then release all allocations.
Tests also cover size selection, CAS races against reown/retirement, stale
client retirement, allocation-free transfer, guarded failure and explicit
OOM. Lookup, heap, SMC, thread-exit and unwind regressions pass. NT services,
time, heap, locks and deterministic interleavings are modeled; these numbers
are not total game RAM measurements or a concurrent Switch test.

Use `dist/pes13-fex3-scratch-reuse-update.zip` for the existing FEX3 install,
or `dist/pes13-fex3-scratch-reuse.zip` for all dependencies. Close from HOME,
copy `switch/` to the SD root and replace the six supplied files. The NRO,
ARM64 ntdll/WOW64 and original stress executable remain byte-identical to
the reserve-fix device baseline. The FEX DLL retains the compact lookup and
v7 heap fixes. Run the default `run_guest_tests=1`; after complete PASS, close
and set it to `0` for PES. Keep logs from each run. The subsequent user report
and PES log are recorded in FEX3-RESULT.md; earlier artifacts remain preserved.

## Previous candidate: compact cache

The compact-heap PES run progresses through DXVK initialization and many game
workers, then stops on an 8 MiB heap reservation (`0xc0000017`). Wine reports
1474 MiB of anonymous reservations, 745 MiB committed, and repeated 25 MiB
lookup views with only 64-188 KiB committed. The native 2048 MiB system range
is excluded, not guest-available RAM. The `406d1388` guest exceptions before
the failure are thread-name notifications; the explicit allocation STOP is
the fatal checkpoint. See the preserved [device result](FEX3-RESULT.md).

The pinned FEX configuration defaults `DisableL2Cache=true`, but the lookup
constructor still reserves the 8 MiB page index and 16 MiB L2 arena. This
package removes those unused reservations when L2 is disabled. Each thread
then reserves only its existing 1 MiB L1 maximum: **25 to 1 MiB**, a 96%
reduction in lookup address reservations, not a 96% reduction in total RAM.
For 32 threads this avoids 768 MiB of unused address space. Dynamic L1 still
starts at 128 KiB and grows up to 1 MiB; full-address L3 lookup, guest address
limits, translation settings and the renderer are unchanged. Explicitly
enabling L2 retains the full 4 GiB index and 25 MiB layout.

An L2-only clear now leaves the L1-only reservation untouched. Clearing all
thread-local caches also resets the L2 backing cursor. Reservation tracking,
bounded commitment and destruction use the actual allocated length. The
emitted dispatcher is unchanged. A once-per-process marker records the
actual cache mode rather than assuming the default:

```text
[FEX3-MEM] v2 omit disabled L2 reservations; lazy commit<=64 KiB
[FEX3-LOOKUP] L2=off reserve=1 MiB/thread; L1=128 KiB..1 MiB
```

Local linked ARM64 tests fit 32 live default caches in the same fragmented
model where the preceding DLL stops at the tenth cache. They cover 296
constructor/destructor lifetimes, 2464 lookups, 120 invalidations and code
replacements, and 16 dynamic L1 growth/shrink/cap transitions. Both L2 modes
retain correct high x86 address lookups and full-reset/refill behavior. Heap,
SMC, allocation, thread-exit gate and exception-unwind regressions pass.
VM, container allocations, locks and time are modeled; these are not a
Switch boot, a fully concurrent kernel test or a game FPS result.

Use `dist/pes13-fex3-compact-cache-update.zip` for the existing FEX3 install,
or `dist/pes13-fex3-compact-cache.zip` for all dependencies. Close from HOME,
copy `switch/` to the SD root and replace the six supplied files. The NRO,
ARM64 ntdll/WOW64 and original stress executable remain byte-identical to
the reserve-fix device baseline. The FEX DLL retains the v7 compact heap.
Run the default `run_guest_tests=1`; after complete PASS, close and set it to
`0` for PES. Save the new runtime log from each run. Hardware results for
this candidate are recorded in FEX3-RESULT.md; it still fails during PES boot.

## Previous candidate: compact heap

The aligned-heap device run creates the 1280x720 Vulkan surface, all four DXVK
compiler threads, and loads `mmdevapi.dll` / `winenxaudio.drv`. It then fails a
32 MiB FEX heap reservation with `STATUS_NO_MEMORY`. The allocator explicitly
traps; native Wine reports `0x80000003` and parks the thread. The application's
remaining black window is therefore consistent with a stopped thread, not
evidence of a completed frame or a diagnosed shader problem. Wine reports
1301 MiB anonymous reservations, 587 MiB committed, plus the 2048 MiB excluded
native heap region. Raw kernel-free ranges can overlap these reservations.

`pes13-fex3-compact-heap` changes rpmalloc's geometry:

| Allocator property | Aligned-heap v6 | Compact-heap v7 |
| --- | --- | --- |
| Span reservation/alignment | 32 MiB | 8 MiB |
| Medium allocator page | 4 MiB | 1 MiB |
| Large allocator page | 32 MiB | 8 MiB |
| Largest pooled block | 8 MiB | 2 MiB |
| Larger requests | Direct allocation | Direct allocation |

The small classes and size-selection formula stay intact. Eight upper large
classes leave the pool and use the existing `PAGE_HUGE` path; the accepted
allocation size is not capped at 2 MiB. Medium/large pages retain at least
three maximum-sized blocks, avoiding the pinned allocator's unsupported
one-block page path. Header geometry, masks, class counts and thresholds are
changed together. Shared constants in `src/fex/horizon_heap.h` and compile-time
assertions protect these relationships. Aligned reservations still have no
extra padding. Large direct allocations may trade some pool reuse for lower
address usage; game performance is not yet measured.

The preflight now checks the two sides of the 2 MiB pooled/direct boundary:

```text
[FEX3-HEAP] v7 spans=8 MiB medium=1 MiB large=8 MiB pooled<=2 MiB
[FEX3-HEAP] PASS span edges, pooled blocks and direct-allocation boundary
```

`tests/fex_compact_heap.py` runs the linked ARM64 allocator and matching Wine
memory helpers with modeled NT VM/TLS. It reproduces the old 32 MiB failure
in synthetic fragmented usable ranges, then fits the full new preflight there.
It checks 350 old/new size boundaries, full-page transitions, multi-span live
blocks, realloc across pooled/direct paths, over-alignment, recycled calloc,
cross-thread free and true failure handling. Twelve thread heaps over three
deterministically interleaved waves retain a constant footprint. For that
specific workload, reservations fall from about 1152 to 288 MiB and committed
pages from about 433 to 109 MiB. This measures the modeled heap workload,
not total game memory, simultaneous kernel execution or FPS. SMC, lookup,
guest tracing, thread-exit gate, unwind and native 8/32 MiB address searches
also pass locally.

The NRO, ARM64 ntdll/WOW64 and original stress executable remain byte-identical
to reserve-fix. Use `dist/pes13-fex3-compact-heap-update.zip` for an existing
FEX3 installation, or `dist/pes13-fex3-compact-heap.zip` for the complete
dependencies. Close from HOME, copy `switch/` to the SD root and replace the
six supplied files. The same forwarder remains valid. Retest with the default
`run_guest_tests=1`; after all original checks PASS, close and use `0` for PES.
Its subsequent PES run fails an 8 MiB reservation as described above. The
earlier packages and complete reserve-fix hardware PASS remain preserved.

## Previous candidate: exact aligned heap

The first subsequent PES run initializes the DXVK/Vulkan device and starts
several guest threads. It then stops at a 64 MiB heap reservation with
`STATUS_NO_MEMORY`. Wine reports 1098 MiB of anonymous views, only 361 MiB
committed, alongside the excluded 2048 MiB native heap area. Raw kernel-free
ranges can overlap those live Wine reservations: they are not all available
to a new allocation. The accompanying guest log is the older stress PASS.

`pes13-fex3-aligned-heap` changes **only the FEX DLL's heap policy and
preflight**. Its NRO, ARM64 ntdll/WOW64 and original guest test remain
byte-identical to the hardware-passed reserve-fix. The pinned rpmalloc used
`size + alignment`: every 32 MiB span reserved 64 MiB. It now passes the
alignment requirement to Wine's `VirtualAlloc2`, which selects the aligned
address under its VM lock. The reservation is exactly 32 MiB, with zero
padding offset. Size classes, page geometry, block limits and commit/free
semantics are unchanged. No release/re-reserve race or forced mapping is
introduced. This halves address reservations **per span**, not total RAM use.

The new preflight reserves a real aligned span, commits/writes both ends,
releases it and checks small/medium/large heap blocks. Expected markers:

```text
[FEX3-HEAP] v6 exact aligned 32 MiB spans; no padding reservation
[FEX3-HEAP] PASS aligned span edges and small/medium/large blocks
```

Local tests execute the old and new ARM64 DLLs: the old padding request fails
in synthetic fragmented Wine-usable holes, while the exact reservation fits.
Tests cover 235 size-class/huge-allocation boundaries, eight simultaneous
thread heaps over three waves, cross-thread free, flat reservation reuse and
opt-in process finalization. NT VM/TLS services are modeled; this does not
execute PES or prove the Switch memory layout. Linked Wine tests also cover
32 MiB alignment with native conflicts in both allocation directions. SMC,
lazy-commit, guest-fault tracing, thread-exit gate and unwind regressions pass.

Use `dist/pes13-fex3-aligned-heap-update.zip` for an existing installation,
or `dist/pes13-fex3-aligned-heap.zip` for all dependencies. Close from HOME,
copy `switch/` to the SD root, replacing the six supplied files, and use the
same forwarder. The update defaults to `run_guest_tests=1`; after the complete
stress PASS, close and set it to `0` for PES. Keep the new runtime log and
guest log separately from the saved baseline. Its subsequent device result
is the black-screen allocation stop described above; it makes no FPS claim.

## Reserved-address recovery and thread cleanup

The earlier unwind-fix runtime stops at `[FEX2-HEAP] STOP reserve failed bytes=0x4000000`.
Its two attempts select `0x18100000` and fail with `EEXIST`, then Wine reports
`STATUS_NO_MEMORY`. The kernel snapshot still has large free intervals. This
is an address-allocation failure, not proof that all physical RAM is full.

Wine tried only one candidate inside each reserved arena. On Horizon its
host reservations are bookkeeping rather than Linux kernel mappings; a stale
reservation promise can conflict with native mappings. The new search visits
aligned candidates within the same arena on `EEXIST`, in the requested
direction and bounds. Other errors stop that search. Before replacement, a
guard checks the mapping metadata and kernel map, rejecting live backing,
section anchors/holes, native stacks and kernel-reserved regions. A transition
reservation protects the candidate until the final mapping is installed.
At most eight successful conflict recoveries receive a `[FEX3-VA]` trace.

The same audit found an independent retention problem: Horizon's server did
not implement `get_object_info`. FEX's `BTCpuThreadTerm` uses that request to
validate `THREAD_TERMINATE`; failure makes it return before destroying its
thread state or finalizing the CRT heap. The actual FEX DLL reproduces that
early return locally. The native server now answers the current-thread pseudo
handle using its implicit access and the real object's reference/handle counts.
Ordinary handles remain unsupported by this query: the shim does not fabricate
access rights without per-handle bookkeeping. The FEX DLL itself is unchanged.

The new build identifies itself once at startup:

```text
[FEX3-MEM] v1 reserved-range recovery and self-thread cleanup query
```

Local tests reproduce the old 64 MiB search failure, verify recovery, probe
30 direction/alignment/layout cases and exercise the native guard and
reservation splits. A separate linked test validates the 64-byte server
reply and feeds it to FEX's real exit gate, which now proceeds to handle
duplication and TEB lookup. Kernel/libnx services and NT requests are modeled;
the subsequent device run passes all four waves, including worker exits and
reuse. This confirms the tested workload, without establishing PES behavior.

## Module index and exception unwind repair

The native bootstrap bypasses PE `LdrInitializeThunk`. It populates its own
module address tree but leaves PE ntdll's private tree empty. Module-name
hash initialization does not populate this separate address index.
`RtlLookupFunctionEntry` therefore cannot locate FEX's unwind metadata. With
the captured entry context, Wine repeatedly treats the frame as a leaf;
PC becomes zero and stack position does not advance. This reproduces the
guest deadline without delivering the x86 exception handler.

The repair exports a pointer to the PE module index and binds it to the native
bootstrap's live tree before guest execution. Both loaders then use one root;
there is no stale root copy or double insertion of intrusive LDR nodes.
Native bootstrap insertion/removal now uses the same Wine red-black algorithm
as PE Wine, replacing the earlier unbalanced insert and empty remove shim.
This preserves the invariants when PE modules are later added or unloaded.

At boot, the real PE `LdrFindEntryForAddress` and `RtlLookupFunctionEntry`
must resolve ntdll, FEX and WOW64 probe functions with the expected image bases.
A missing matching PE DLL, conflicting nonempty index or absent unwind table
stops startup explicitly. The success marker is:

```text
[FEX3-UNWIND] PASS shared module index; ntdll/FEX/WOW64 unwind tables found
```

`tests/fex_unwind.py` executes the actual native handoff, PE lookup/dispatcher,
FEX capture wrapper, WOW64 guest-frame builder and Wine stack unwind. It
reproduces the unshared-index loop, then verifies the x86 fault record/context
and return to the CPU simulation loop after binding. Another 576 mixed
native/PE tree operations check ordering, parent pointers, minimum node and
red-black balance through root changes and deletion. NT Get/SetContext,
final continuation and native export lookup are modeled; actual x86 VEH
execution, parallel kernel behavior and PES compatibility remain device tests.
The unwind metadata format follows Microsoft's
[ARM64 exception handling specification](https://learn.microsoft.com/en-us/cpp/build/arm64-exception-handling?view=msvc-170).

## Retained first-guest-fault diagnostics

The earlier guest-fault-trace log shows all four workers waiting in the first generated
`A1 moffs32` read of their own `PAGE_NOACCESS` allocation. The guest handler
should recognize that exact access violation, set EAX, advance EIP by five
bytes and resume at RET. The v4 trace locates the stop after native dispatch
and before x86 handler entry. The normal workload, 30-second worker deadline and
exception acceptance conditions are unchanged.

New diagnostics:

- `[FEX3-GEX] v1` identifies the DLL. Each of the first 12 candidate faults
  gets a ticket and native thread ID. Stages bracket SMC locking/checking,
  JIT classification, guest context reconstruction, leaving simulation and
  `NtRaiseException`. `guest-context` prints guest EIP/ESP. `raise-return`
  records an unexpected return's status without changing its handling.
- `[FEX3-SEH]` has its own ticket series and the same native thread ID. It
  brackets entry to native Wine's exception dispatcher, stack preparation
  and continuation into ARM64 PE ntdll. Follow thread IDs across the two
  series; their ticket numbers are independent. Both series stop after
  their first 12 candidates, rather than tracing every page fault.
- `[FEX3-LAST]` at process exit retains the last fault stage per native thread,
  even when startup faults used up the printed trace allowance. Updates use
  fixed atomic storage without file I/O; at most 32 rows are printed. Stages
  are 1 before Wine VM handling, 2 after VM handling, 3 before FEX callback,
  4 after FEX callback (`status` is handled/not-handled), 5 native exception
  dispatch, 6 continuation into PE ntdll. An in-progress row is marked busy.
- `[FEX3-GUEST] v4` counts handler entries before TLS lookup. On timeout it
  reports each worker's handler calls, handler phase and captured exception
  fields using atomic reads. Handler phase 1 means entry/snapshot complete,
  2 means the exception failed the existing strict checks, and 3 means its
  context was updated for continuation. The fields are individual snapshots,
  not a transactionally consistent trace if a worker is still running.

The new route logs are diagnostic overhead, not a performance measurement.
Return both logs after a single test; a hang followed by `FAIL worker deadline`
is still useful because it retains the original failure and records its route.

## Worker memory failure and repair

The earlier SMC-fix runtime requested `0x9800000` (152 MiB) for another FEX thread's
lookup cache. The largest available contiguous interval was only 105 MiB.
The allocator returned `STATUS_NO_MEMORY` (`0xc0000017`), yet the old lookup
constructor published the failed null reservation as a tracked interval.
The Wine overcommit handler also committed an entire queried reservation on
first touch. Later commits and a heap reservation failed too. This is evidence
of virtual address fragmentation and excessive commitment, not a GPU failure
or proof that all physical RAM was exhausted.

The earlier memory-fix kept the full 8 MiB index for the 4 GiB x86 address
space, caps the L2 backing at 16 MiB and caps L1 at 1 MiB. Each thread reserves
25 MiB instead of 152 MiB. A main thread plus four workers therefore needed
125 MiB of lookup reservations instead of 760 MiB. These figures exclude
translation buffers, IR, heaps, stacks and guest allocations.
The compact-cache candidate described above additionally omits the index
and L2 backing when L2 is disabled.

L2 retains its existing eviction and L3 fallback; dynamic L1 resizing remains
enabled with its original minimum. Smaller caches can increase misses or
evictions in a large game workload; this change solves a demonstrated bring-up
constraint and is not a measured game performance improvement.

The overcommit path commits at most 64 KiB from the faulting page, clipped to
both the tracked interval and the NT region. It rejects null, malformed,
unowned, guarded or non-writable committed ranges and propagates allocation
failures. Execute faults bypass data commitment. A failed cache reservation
stops explicitly before registering a null interval. Existing decommit/free
paths remain in use.

The stress test keeps four workers per wave, four waves and its original
deadline. Timeout diagnostics now report each worker's atomic phase and round:
0 not entered, 1 TLS/start wait, 2 allocation/protection, 3 first generated
call, 4 original code passed, 5 SMC update/call, 6 guest fault, 7 iteration
complete, 8 workload finished. These are snapshots, not a synchronized trace;
there is still no per-iteration file logging.

## SMC failure and repair

The failed branch follows a successful call to original x86 code returning
42. A worker then changes its immediate operand without calling
`FlushInstructionCache`; execution fails to return the new value. The old log
does not record the actual value. The new test logs the worker, round, code
address, expected result, actual result, stored immediate and Wine protection
on failure, without per-iteration file writes.

Horizon section aliases can remain writable even when Wine reports read-only
protection. FEX's normal protection-based tracking cannot rely on a write
fault for those mappings. It is not yet proven that this is the exact mapping
in the failed worker, or that SMC is the sole cause of the PES startup stop.
The supplied PES log ends with a successful `imm32.dll` attach/return; it does
not establish a missing DLL or a crash at that loader message.

The adapter now walks every executable-permission interval in a decoded block.
Blocks touching tracked writable executable memory use FEX's existing
per-instruction code-validation and invalidation path. Read-only blocks keep
the unchecked path; normal MTRACK invalidations remain enabled. This also
covers blocks crossing RX/RWX boundaries. Unknown or inconsistent ranges
conservatively require validation. No change weakens the stress test's
no-flush requirement. FEX's existing CRC instructions are supported by
Cortex-A57 according to Arm's [TRM, table 4-34](https://documentation-service.arm.com/static/5e906b3d8259fe2368e2aa8a).

Failed SMC protection calls now produce at most eight diagnostics. Failed
unprotection is no longer reported as a handled write fault, which would
otherwise resume the same faulting instruction indefinitely. This package
prioritizes correct guest execution; the added checks' game performance has
not been measured.

## What changed

- Ordinary Horizon faults now use distinct handler stacks and register dumps
  instead of libnx's shared storage. A bounded pool holds 64 live handlers;
  nested faults get a separate slot. A slot is retired only after the final
  register read during context restoration. Exhaustion aborts explicitly.
- Native-to-FEX exception callbacks install the current Wine TEB in x18 and
  restore native x18 on return. Native helpers may use x18 as scratch.
- The native Wine `call_user_exception_dispatcher` stub is replaced by an
  ARM64 exception frame and continuation into the loaded PE ntdll dispatcher.
  Wine's WOW64 path can then deliver real guest exceptions to x86 handlers.
- The single NRO can launch the original stress test or PES. All runtime,
  loader and registry paths use `switch/pes13-fex/`, including the older
  fallback paths. The PES image-address reservation is retained.
- The package includes the matched Wine dependencies, existing DXVK D3D9
  payload and XInput modules. The NRO links Mesa/NVK and no Box64 engine.
  This is backend integration, not a new graphics optimization.

## Install and test

1. Extract **`pes13-fex3-native-lookup.zip`** at the SD root, replacing the packaged
   files in the existing FEX prefix. It creates
   `switch/pes13-fex/`. The existing Box64 and FEX2 folders are independent.
   Keep your personal `drive_c/KONAMI/` profile before applying the full
   package, then restore it: the package includes the generated settings preset.
   For an existing ABI-2 installation, use the smaller
   `pes13-fex3-native-lookup-update.zip` described above: it includes only
   the FEX DLL and ARM64 ntdll under `switch/`, preserving game/profile and
   configuration. Close with HOME -> X before copying.
2. Create a Sphaira forwarder for
   **`sdmc:/switch/pes13-fex/pes13-fex.nro`**, with **32-bit address space,
   no alias, 4 cores**. Run in full application mode, as in the FEX2 PASS.
3. Leave `run_guest_tests=1` in `configuration.ini` for the first run. No game
   data is needed for this test. It first checks four simultaneous native
   exception handlers, then runs four waves of four x86 workers. Workers
   exercise TLS, SSE, x87, automatic self-modifying-code invalidation and
   handled access violations with context resume.
   The runtime must show `[FEX3-MEM] v3 resident native L1`
   and, with the default configuration, `[FEX3-LOOKUP] L2=off native=1 MiB/thread`,
   and `[FEX3-SMC] v1 byte validation for writable guest blocks`.
   The runtime must also show `[FEX3-GEX] v1` and the guest log must begin
   `[FEX3-GUEST] v4`, as in the preceding diagnostic build. The new runtime
   must show `[FEX3-UNWIND] PASS shared module index`. No forwarder change
   is needed at the same NRO path.
4. Success requires both of these checkpoints:

   ```text
   [FEX3-FAULT] PASS 64 roundtrips; 4 overlapping handlers; all slots released
   [FEX3-GUEST] PASS all checks: 16 workers, 256 SMC updates, 256 handled faults
   ```

   The runtime then exits with code 0 and parks. Close with HOME -> X.
   If a check fails or the run stops, return the logs before trying game mode.

## Launch PES with the same NRO

After the stress test passes on Switch:

1. Copy your installed game from the working Box64 prefix's `drive_c/PES13/`
   into `switch/pes13-fex/drive_c/PES13/`. Include `pes2013.exe`, its game DLLs
   and the `img` directory. This package does not include those game files.
2. Extract the FEX3 package once more **over the new FEX folder** so its matched
   `d3d9.dll`, quiet renderer settings and XInput preset take precedence over
   any older DLL/configuration copied with the game.
3. Copy your private `pes13-install.reg` from the working Box64 folder to
   `switch/pes13-fex/pes13-install.reg`. Copy your working
   `drive_c/KONAMI/Pro Evolution Soccer 2013/`
   profile to the same relative path under FEX. The package supplies only the
   project's generated XInput `settings.dat`; copying your existing profile
   afterwards preserves your current settings and saves.
4. Set **`run_guest_tests=0`** in the FEX folder's `configuration.ini`. Open the
   same forwarder. The log should say `[FEX3] mode=PES13`, followed by
   `selected libwow64fex.dll`. No NRO swap or second forwarder is needed.

The source profile is
`switch/pes13-nx/drive_c/KONAMI/Pro Evolution Soccer 2013/`; the destination is
`switch/pes13-fex/drive_c/KONAMI/Pro Evolution Soccer 2013/`. This follows the
observed `C:\KONAMI\...` path from Settings Debug and the user's working
Box64 installation. The earlier Documents path in this guide was incorrect.
Copy the entire working profile, including `settings.dat` and any save
subdirectories, after applying the package. The new FEX game run remains
unverified; this migration preserves the known working relative path.

Do not copy the old prefix's root `configuration.ini`, `system.reg`,
`user.reg`, transient shared-memory files, `windows/` or `share/` over FEX.
The new registry is created in the isolated prefix. Box64 flags are ignored
by this backend. The game and test have separate purposes: a stress-test PASS
does not guarantee PES compatibility.

```text
switch/pes13-fex/
  pes13-fex.nro
  configuration.ini
  pes13-install.reg                 # copy your own, for game mode
  drive_c/
    fex-stress.exe                  # original test, no game code
    PES13/                         # your game + packaged D3D9/settings
    KONAMI/Pro Evolution Soccer 2013/  # working settings.dat and saves
    windows/                       # matched Wine/FEX/XInput modules
    dxvk/d3d9.dll
  share/wine/
```

Return `switch/pes13-fex/fex-runtime.log` after either mode. The original
test writes `switch/pes13-fex/drive_c/fex-guest.log`. Save the first run's
logs before relaunching because the runtime log is overwritten at startup.
For a successful game boot, report menu, controller, audio, match/replay
behavior and CPU/GPU/RAM clocks. Use the same clocks and 1280x720 preset for
the first comparison with Box64.

## Local validation and reproducibility

FEX remains at `e2f973fe931e6dc2ce523795e51ca1ac3ca85816`; the compact heap,
allocation bounds, physical counter and callback fixes are retained. The retained
FEX DLL is `340f33f615e0c9fa9b4ef3b6c573472e37514997ab9bb7fcc3c3eabec2c44ca9`.
It is **not** the FEX2 hardware-tested DLL
`22ad6747d1b8a1f46e4da95eb760a7a596dadc76c8278fd9c8b62d0c677dd968`.
The failing guest log, supplied PES runtime log, original package and build
receipts from the initial SMC failure are preserved in `local/fex3/smc-fix/before/`.
The allocation/deadline logs and the SMC-fix update are preserved in
`local/fex3/memory-fix/before/` with input hashes.
The earlier phase-6 timeout logs, memory-fix update and receipts are preserved
in `local/fex3/guest-fault-fix/before/` with input hashes. Diagnostic build
receipts and tests are under `local/fex3/guest-fault-trace/`.
The v4 timeout trace, preceding diagnostic overlay and reproduction receipt are
preserved under `local/fex3/dispatch-fix/before/`. The new build receipt and
`unwind-tests.json` are under `local/fex3/`.
The first-wave-PASS/second-wave-allocation-failure logs, preceding package
and old ELF are archived under `local/fex3/reserve-fix/before/`. The new build,
reservation and thread-exit regression receipts are bound to the new ELF hash.
The subsequent complete hardware PASS logs and result receipt are archived
under `local/fex3/hardware-pass/`; see [FEX3-RESULT.md](FEX3-RESULT.md).

Build through WSL, without Docker:

```sh
python3 tools/build-fex-module.py --horizon --build-root /home/blekjek/pes13-build --jobs 4 --output-dir /mnt/d/Dev/Switch/SwitchHub/pes13-nx/local/fex3/jit-growth/module
python3 tools/build-fex-runtime.py --integration --build-root /home/blekjek/pes13-build --jobs 4
```

From the Windows checkout, with Python, Unicorn, pyelftools and pefile:

```sh
python tests/fex_context.py local/fex3/reference/pes13-fex.elf
python tests/fex_exceptions.py local/fex3/reference/pes13-fex.elf --output local/fex3/exception-tests.json
python tests/fex_dispatch.py local/fex3/reference/pes13-fex.elf --output local/fex3/dispatcher-tests.json
python tests/fex_unwind.py local/fex3/payload/ntdll.dll local/fex3/fd-routing/module/libwow64fex.dll local/fex3/payload/wow64.dll --elf local/fex3/reference/pes13-fex.elf --output local/fex3/unwind-tests.json
python tests/fex_reservations.py local/fex3/reference/pes13-fex.elf --output local/fex3/reservation-tests.json
python tests/fex_thread_exit.py local/fex3/reference/pes13-fex.elf local/fex3/payload/ntdll.dll local/fex3/fd-routing/module/libwow64fex.dll local/fex3/payload/wow64.dll --output local/fex3/thread-exit-tests.json
python tests/fex_guest_reference.py --stress
python tests/fex_smc.py local/fex3/fd-routing/module/libwow64fex.dll --output local/fex3/fd-routing/smc-tests.json
python tests/fex_memory.py local/fex3/fd-routing/module/libwow64fex.dll --before local/fex3/smc-fix/module/libwow64fex.dll --output local/fex3/fd-routing/memory-tests.json
python tests/fex_lookup.py local/fex3/fd-routing/module/libwow64fex.dll --before local/fex3/compact-heap/module/libwow64fex.dll --output local/fex3/fd-routing/lookup-tests.json
python tests/fex_alloc.py local/fex3/fd-routing/module/libwow64fex.dll --output local/fex3/fd-routing/alloc-tests.json
python tests/fex_compact_heap.py local/fex3/fd-routing/module/libwow64fex.dll --before local/fex3/aligned-heap/module/libwow64fex.dll --ntdll local/fex3/payload/ntdll.dll --output local/fex3/fd-routing/heap-tests.json
python tests/fex_guest_trace.py local/fex3/fd-routing/module/libwow64fex.dll --output local/fex3/fd-routing/guest-trace-tests.json
python tests/fex_scratch.py local/fex3/fd-routing/module/libwow64fex.dll --before local/fex3/compact-cache/module/libwow64fex.dll --output local/fex3/fd-routing/scratch-tests.json
python tests/fex_fd_routing.py local/fex3/reference/pes13-fex.elf --before local/fex3/fd-routing/before/pes13-fex.elf --output local/fex3/fd-routing/fd-routing-tests.json
python tools/package-fex3.py
```

The linked ARM64 tests pass for full context restore, 64 held fault frames,
pool exhaustion, nested frames and immediate hostile reuse after release.
The dispatcher test checks the Wine ARM64 frame layout, failure paths and
PE callback TEB boundary. These model kernel/NT boundaries; they do not run
concurrent Switch CPUs or the full WOW64 exception route. The original x86
stress program passes on the Windows PC, which validates its expectations,
not FEX execution. The package records these separate scopes and hashes.

The SMC tests compile and execute 3,691 permission-policy cases, including
RX/RWX boundary crossings, holes and overflow. The actual linked FEX emitter
generates and runs guards for x86 lengths 1 through 15 with three register
assignments. All 2,880 tested bit changes are detected with guest memory still
writable and no protection fault; unchanged code is accepted, including the
reported MOV-immediate shape. Reads ending at an unmapped page boundary do
not overread. These tests cover selection and generated checks, **not** a full
translated execution, all-thread invalidation or the Horizon kernel.

The memory test executes the linked ARM64 constructor, destructor, lazy-commit
adapter and L2 eviction routine against a bounded NT/configuration model. It
reproduces the old 152 MiB failure and null publication, then fits 32 default
1 MiB caches, or five explicitly enabled 25 MiB caches, in a synthetic subset
of fragmented intervals. The 296 cache lifetimes cover dynamic/static L1,
complete release and unchanged 4 GiB indexing when L2 is enabled. The separate
lookup test executes full-address L1/L2/L3 lookup, erasure/replacement and
dynamic L1 resizing. Additional checks cover clipped lazy commits, query/commit failures,
protected pages, decommit/refill and explicit stop on failed reservation. This
does not validate full translated execution, concurrent kernel behavior or FPS.

The diagnostic test executes the DLL's logger/ticket code, verifies saturated
suppression after 12 faults, fixed-buffer bounds for all internal stage names,
invalid-ticket suppression and x18 preservation across a hostile host logger.
The native dispatcher test models diagnostic I/O and verifies that context
and frame behavior is unchanged. These checks do not prove that Wine's full
PE unwinder delivers a guest exception on Switch.

The user's local PES EXE and companion DLL were previously checked against an
isolated copy of the diagnostic payload. All 72 reachable PE modules passed the import,
delay-import and export-forwarder audit with the packaged API-set schema.
This is a static dependency check, not a successful game launch. No game
files from that private audit are copied into the public ZIP.

The packager selects dependencies only from `config/runtime-files.json` by
exact hash, overrides ARM64 ntdll/WOW64/FEX/DXVK explicitly, audits imports and checks
the NRO icon/NACP and every ZIP entry. Game executables, private metadata,
personal saves and logs are excluded. Build outputs and detailed local
evidence remain under ignored `local/fex3/` and `dist/`.

## Startup probe after the JIT-growth run

The September 25 JIT-growth log stops after Wine activates a new top-level
popup, before a Vulkan present is logged. Its 16 KiB, 16 MiB and 32 MiB JIT
allocations succeeded; it does not show the earlier 64 MiB allocation failure.
The user closed the loading/black screen in under two minutes. With
`production=1`, the old progress reporter was called every minute and only
emitted every other call, so that log has no useful elapsed-time samples.

The `pes13-fex3-startup-probe` NRO records the number of Vulkan presents and
framebuffer frames every five seconds for the first two minutes, and emits its
existing progress and thread summary about every ten seconds in that window.
It also records the class, title and owner of non-child windows when shown.
These probes are bounded; normal production logging resumes after two minutes.
The NRO-only update leaves the installed DLLs, `configuration.ini`, game and
user profile untouched. Save each `fex-runtime.log` before the next launch,
which truncates it. This is a diagnosis build; it does not claim a startup or
FPS fix until the new on-device logs identify a cause.
