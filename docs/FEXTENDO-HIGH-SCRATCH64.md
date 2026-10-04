# HIGH compiler-overlap fix candidate: 64 MiB scratch reserve

## Captured failure

The live-freeze reproduction has transition SHA-256
`576a22ab05af9b93a9da09dc9a5019c84ff49b680f2f26f856e63c4f6bab8561`.
It uses NRO build ID
`89c964e220ce973059f5571722776c270681ed55000000000000000000000000`.
The user's stopwatch estimate is around 7:10; the recorder measures its own
bootstrap and first-frame origins, so these timestamps should not be treated
as exactly identical.

At 438,601 ms after crash-recorder bootstrap (419,036 ms after first-frame
trace initialization), thread handle `81ff`, Wine TID `4`, requests another
8 MiB compiler scratch buffer. All 32 MiB of the reserve are live in three
allocations. Normal `aligned_alloc(4096, 8388608)` also fails with errno 12.
The new return-address record resolves to `allocate_scratch+0x278` in the
exact native ELF, not a graphics-driver allocation site.

FEX then records `STOP compiler scratch failed bytes=0x800000`. The fatal
helper traps at FEX RVA `0x14bb88`, which Wine reports as status `0x80000003`.
The live snapshots at 421,862 and 428,092 ms show the main thread parked in
`pes13_fex_wine_exception_handler+0x634`, with negligible CPU-tick advance.
The failure is captured directly in `crash.log` as FEX_STOP and an unhandled
native exception. This identifies the final thread halt in this run.

The user observed the crowd still moving when gameplay froze. In this log,
presentation also stops later: the final five samples hold at 21,925 presents,
and final frame age reaches 9,003 ms. The earlier reproduction kept presenting;
we do not assume every earlier freeze has this exact cause.

The scratch arena is being released and reused during the session (13 returns
and 16 successful arena allocations by the failure). This is not evidence that
the native arena never frees anything. The captured problem is a live overlap
that exceeds its capacity while the ordinary heap can no longer satisfy an
8 MiB contiguous allocation. Around 129 MiB is reported free in aggregate at
the end; the largest ordinary-heap free block was not measured.

## Change and limits

This candidate reserves a contiguous **64 MiB** before guest and DXVK workers
start, instead of 32 MiB. It can hold the observed 16+8+8 MiB live buffers and
another 8 MiB request without depending on the fragmented ordinary heap.
It has an additional 24 MiB margin beyond that 40 MiB overlap. The existing
arena allocation, release, ownership, coalescing and libc fallback algorithms
are unchanged. No live buffer is stolen, moved, resized or freed early.

The capacity is a build-time option with only 32 and 64 MiB accepted. Startup
can fall back to 32, 16 or 8 MiB if the requested reserve cannot be allocated;
the actual capacity is logged. The maximum additional reserved memory is
32 MiB. It comes from the same native heap, so other allocation pressure must
be checked on device; this is not an increase to the process memory limit or
a general solution for every out-of-memory condition.

`SCRATCH_V3` identifies this candidate. A full reserve reports
`capacity=67108864`. Keep CRASH_V2 and the existing six-second live snapshots
for verification. The prior run measured snapshot duration 225–622 us
(median 382 us), excluding formatting and SD writes; this is not a complete
measurement of diagnostic overhead.

The production FEX DLL and its ownership protocol are unchanged, as are
DXVK, graphics presets, input, keyboard, clock policy and game timing. The
runtime lock is unchanged. Only the native NRO and diagnostics marker install.
No ZIP is produced. Rollback restores the exact tested 32 MiB live-freeze NRO.

## Verification

Host ASan/UBSan tests cover startup capacities 0/8/16/32/64 MiB, concurrent
requests, buffer boundaries, fragmented holes, invalid interior releases,
larger contiguous reuse and normal libc fallback. A regression executes the
actual prior and new ARM64 callbacks under the same simulated ordinary-heap
failure: keep 16+8+8 MiB live, request 8 MiB. The prior 32 MiB NRO fails;
the 64 MiB candidate succeeds and preserves all live buffer contents.
Partial startup capacity still fails honestly when all owned memory is busy.

Controller, keyboard, direct crash persistence, allocation-callsite recording,
live snapshots and silent-path checks run on the new ELF with modeled OS
services. Source integrity confirms only the reviewed capacity definition and
four existing allocator hooks differ from the frozen native adapter. These
tests do not reproduce PES, real kernel allocation or long-session GPU load.
The build remains unverified on Switch until the next user reproduction.

## Console check

Use HIGH + Default DXVK with the same fixed clocks. Play past the previous
7:10 trigger and half time, ideally 12–15 minutes, including ball-out,
replay, corner and free-kick transitions. Capture transition.log and crash.log
before relaunch, including a successful run. If frozen, allow 15–20 seconds
before closing with HOME > X > Close. Check that SCRATCH_V3 reports a full
64 MiB reserve, whether failed stays zero, and whether peak_used exceeds
32 MiB without stopping the main thread. Do not infer success only from a
moving crowd or from the absence of a system crash dialog.
