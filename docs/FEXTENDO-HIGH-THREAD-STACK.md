# HIGH native thread stack candidate v1

## Evidence and scope

The supplied HIGH transition log has SHA-256
`d3b08b921dc17ac37e593dabeebc128773bf06b69940de0d91bf5e4889832d6c`.
Its crash header identifies `high-page-store-v1`, build ID
`4a0f8d5c633f6d653b6252d76e4c80966460c832000000000000000000000000`.
No fatal record was captured. The user reports freezing around two minutes,
with MEDIUM and lower unaffected.

The trace starts 17.720 seconds after crash bootstrap. At trace 127.759 seconds
(about 2:25 from bootstrap), native `threadCreate+0x138` fails
`aligned_alloc(4096, 1052672)` with ENOMEM. This is libnx stack/TLS storage,
outside the Wine backing allocation fallback. Wine reports four recovered
allocations, all released, with zero fallback or rollback failures. FEX's
64-MiB scratch arena reports zero failures. The allocator still reports about
101 MiB of free plus untaken memory at the end, consistent with fragmentation.

The original libnx call site returns `LibnxError_OutOfMemory` when that
allocation fails. The log does not establish that this is the only cause of
the match freeze. Present continues while the match appears frozen, so its
rate must not be interpreted as advancing gameplay. There is no corresponding
MEDIUM capture proving a quantitative difference in memory consumption.

## Change

At bootstrap, reserve at most eight separately allocated, page-aligned native
stack slots. Each holds the unchanged 1-MiB stack plus the linked TLS size and
`struct _reent`, rounded to 4096 bytes (about 8 MiB total). Partial or failed
initialization leaves the normal allocator available.

Link wrappers around `threadCreate`, `__libnx_aligned_alloc` and `__libnx_free`
preserve the original libnx functions and ABI. A thread-local guard restricts
fallback to automatic stack allocations during `threadCreate`, at the usual
alignment, and for stacks no larger than 1 MiB. The normal allocator is always
tried first. Caller-owned stacks and unrelated libnx allocations do not borrow
the reserve. No stack size, priority, CPU mask, entry point or TLS layout is
changed. The frozen FEX DLL and production runtime lock are unchanged.

Successful threads hold their slots until normal libnx teardown. Returning a
slot requires every source page to be writable heap memory without borrowed,
IPC or device attributes. A failed query or incomplete unmap quarantines the
slot. This also protects libnx's create-error path, which does not itself check
the rollback unmap result. Interior and duplicate releases are rejected.
Metadata is static; lease/release uses atomic slot state, without a lock held
across kernel calls. Upstream lifecycle reference:
[libnx thread.c](https://github.com/switchbrew/libnx/blob/master/nx/source/kernel/thread.c).
The delivered linked libnx machine code, rather than upstream HEAD, is the
authority for the regression tests.

## Diagnostics and validation

`THREAD_STACK_V1` separates recovered allocation attempts, pool exhaustion,
quarantined slots and final `threadCreate` failures. `EVENT kind=12` carries
the native Result, requested stack size, calling thread and time. Logging
remains on the existing bounded maintenance worker. The crash header identifies
`high-thread-stack-v1`; absence of a fatal record does not prove a clean exit.

The host suite checks no/partial/full reserve, normal allocation, exhaustion,
caller-owned buffers, nested allocation eligibility, concurrent leases,
recycling and unmap/query failure quarantine under ASan/UBSan. The ARM64 suite
executes the linked old/new libnx stack creation and teardown against modeled
allocator and Horizon services, including TLS and reent initialization.
Receipts are required before packaging; they do not certify Switch gameplay.

Retain HIGH and the same renderer/clocks for the next comparison. Exercise
events through full-time/result, then a subsequent match if possible. Preserve
`transition.log` and `crash.log` before relaunch. A freeze with no final thread
creation failure requires following the remaining live-thread evidence rather
than increasing the reserve blindly.

Build with the existing pinned input-fix recipe plus `--thread-stack-reserve`.
The folder overlay contains only the NRO and diagnostic marker under `switch`;
its rollback restores the exact previous page-store NRO.
