# General fragmented FEX CPU heap candidate v1

## Evidence

Input archive: `local/high-freeze-review/7e95ef2c5ba5`. Full padded crash file
identifies `high-scratch-pages-v1`, build ID
`703d624569130f8e2e340626281b7cb6b07efda6000000000000000000000000`.
`FEX_STOP` at 405048 ms (6:45.048) reports `lookup reserve failed` for
1048576 bytes. The last transition sample corresponds to bootstrap
404610.313 ms, 438 ms earlier. It still presents frames, with 109387152 bytes
free in the native allocator and 2801664 bytes untaken: 112188816 total
(106.99 MiB). This is a nearby sample, not an exact measurement at the fatal
allocation. The captured record explains the fatal allocation, but does not
contain a separate final native exception or prove every contributing cause.

The existing compiler arena held 24 MiB, its largest free run was 32 MiB.
It intentionally reserves whole 8-MiB units for compiler buffers. Ordinary
1-MiB lookup allocations bypass it. The former fragmented fallback also
rejected every request below 8 MiB, so this request had no recovery path.
In this run Wine backing recovered and released two 6225920-byte buffers;
the stack fallback was unused and all 144 recorded thread creations succeeded.
There were no scratch-page fallback attempts before the final snapshot.

This supports native heap fragmentation as the leading explanation; it does
not establish a RAM clock requirement or prove the console exhausted all RAM.
The process allowance is 2 GiB. Frequency does not increase that capacity.

## General allocation policy

Retain the fast ordinary allocation path and the 64-MiB compiler reserve.
After normal allocation fails, a shared native fallback handles **all nonzero
page-rounded sizes** within a bounded 128-MiB total live budget. There are no
1-MiB or 16-MiB special cases, event checks, PC checks, or match timers.

The frozen FEX ABI exposes scratch and private CRT allocation callbacks.
Both now use the same fallback. Scratch includes the L1 lookup table and
compiler workspaces. Private heap covers native FEX containers/CRT data;
its existing header, requested size, alignment calculation and free protocol
remain unchanged. Calloc/realloc continue to use the frozen PE implementation
and the same callbacks. Realloc failure keeps the old allocation alive.

Start with chunks at most 1 MiB. Reduce failed requests by page-rounded halves
down to one 4-KiB page, correctly handling non-power-of-two tails. Reserve
one contiguous virtual interval using libnx, map those chunks into a RW
alias, and return it only after every map succeeds. This is native MMU-backed
memory, with no per-read translation in software or per-frame copy.

Instead of eight arrays of 1024 descriptors, 128 possible owners share 32768
static descriptors (about 1 MiB). The descriptor count can represent the
entire 128-MiB budget even if every source is only one page. Descriptors are
reused on release and do not require heap allocation during recovery. There
is no new resident data reserve. The shared byte and owner limits keep a real
shortage bounded; they are explicit limits, not a claim of unlimited recovery.

Allocation, kernel operations and backing frees run outside the metadata
lock. Failed operations unwind all completed mappings. Failed unmaps retain
their reservation and sources in quarantine, preventing borrowed pages from
being freed/reused. Monotonic alias bounds let ordinary heap frees bypass
ownership scanning and its lock. Successful releases return both data and
metadata; lookup teardown and container destruction retain their original
ownership behavior.

The fallback is intentionally limited to ordinary **CPU data**. JIT executable
memory, GPU/device buffers and guest pages requiring Wine protection/section
semantics cannot safely use a generic RW stack alias. The existing Wine
segmented page-store and native stack fallback remain active for those
respective allocation paths. The pinned FEX DLL, host ABI, DXVK, graphics
preset, limiter and clocks remain unchanged.

Kernel requirements are based on [libnx memory syscalls](https://switchbrew.github.io/libnx/svc_8h.html)
and [virtual-memory reservation implementation](https://github.com/switchbrew/libnx/blob/master/nx/source/kernel/virtmem.c).
`svcMapMemory` borrows its source pages; `virtmemFindStack` and reservation
creation run under the libnx virtual-memory lock.

## Validation and delivery

Require the previous compiler/Wine/stack/input/keyboard/fatal-file regression
suite plus the general fragmented-heap ARM64 regression. Reproduce the old
1-MiB lookup failure and a private-heap failure against the prior ELF, then
show both recover in the new callback. Exercise variable sizes, 4-KiB fragments,
non-power-of-two tails, alignment/header/free ownership, many simultaneous
owners, buffer reuse, capacity exhaustion, and failure preserving live data.
Host tests use real shared mappings and inaccessible source pages under
ASan/UBSan, with concurrent allocation/release and unmap quarantine cases.
Binary tests run the actual linked ARM64 callbacks but model the OS and heap;
they do not measure Switch performance or prove the device crash is fixed.
An additional linked-binary check places scratch and CRT aliases above 4 GiB
to verify pointer width/alignment and verifies ordinary small heap frees
bypass the fallback ownership lock while those aliases remain live.

Keep `SCRATCH_PAGES_V1` field compatibility: it now reports shared CPU data
fallback activity, including private heap, not compiler buffers alone. The
build receipt has `scratch_pages_version=2`; crash header identifies
`high-fragmented-heap-v1`. `PAGES_V1` and `THREAD_STACK_V1` remain separate.

Deliver a folder, no ZIP, with only the NRO and diagnostic opt-in under
`switch/`. Preserve the exact prior NRO in `rollback/`. Keep renderer/clocks
constant, repeat events through half/full-time and ideally a second match.
Check returns/live bytes across repeated events, and collect both logs before
relaunch. A true capacity, virtual-address or kernel-map failure can still
fail safely and must be diagnosed using its specific evidence.

## Local result

Build completed and all 21 required validation receipts passed. The new
ARM64 regression reproduces the old 1-MiB lookup and private-heap failures,
then recovers both; it also checks 24 size/fragment combinations and 128
simultaneous fallback owners with mixed reuse. The real-mapping sanitizer
suite covers the larger buffers at 4-KiB fragmentation as well. Executable
hashes and unchanged native dependencies are recorded in the package evidence.
NRO SHA-256: `b410d7b9e7790fa7d062208897faf089e52a2bc5837c89e7c0268ca4ecc7f63a`.
Build ID: `d81ae67fd97b9e733e0da887a142fe69b124a384000000000000000000000000`.
Hardware validation is still pending.
