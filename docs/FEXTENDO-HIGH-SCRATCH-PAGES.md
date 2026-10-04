# HIGH fragmented compiler workspace candidate v1

## Observed failure

Input logs are archived under `local/high-freeze-review/b7ecbcb91f8a`.
The source transition log identifies `high-thread-stack-v1`, NRO build ID
`93edee3071779684da7a3ddd9bd193f61874bede000000000000000000000000`.
At trace 129.812 seconds, `allocate_scratch+0x278` fails an aligned 16-MiB
allocation. The trace starts 16.573 seconds after bootstrap, placing this at
about 2:26 from bootstrap. FEX then prints
`[FEX2-HEAP] STOP compiler scratch failed bytes=0x0000000001000000`, traps
at its known `HeapFailure` RVA 0x14bb88, and parks native worker 0x3f019a.
Presents stop at 5746 by the final sample. The padded `crash.log` also captures
`FEX_STOP` at 146385 ms and `UNHANDLED_NATIVE_EXCEPTION` at 146388 ms, with
the same worker, 16-MiB request and breakpoint PC. These records confirm the
fatal compiler failure; the subsequent whole-process termination is not
recorded separately.

At failure, the preallocated FEX arena holds 56 MiB across five live buffers;
its largest remaining interval is 8 MiB. Native allocator free space is about
116 MiB (121793376 bytes), with about 5 MiB more untaken heap. This is a
failure to obtain a sufficiently large contiguous allocation under pressure,
not proof that all physical RAM is consumed. All 98 native thread creations
succeed and the eight emergency stacks remain unused. Wine's segmented page
fallback has no failures and is not used in this run.

The trace reports a 2-GiB process memory allowance. It is not a measurement
of the console's entire physical memory capacity. MHz describes memory clock,
not capacity. The input does not establish that increasing RAM clocks solves
the allocation failure; no minimum MHz requirement is justified.

## Native fallback

Keep the existing 64-MiB arena, ordinary heap path, frozen PE DLL and host ABI.
Only after both allocation paths fail, assemble a large compiler workspace
from separately allocated, page-aligned heap chunks. Start at 1 MiB and shrink
to 64 KiB if fragmentation prevents a chunk allocation. Up to eight fallback
workspaces are tracked with static metadata; each request is bounded to
8–64 MiB and total held fallback space to 128 MiB. No extra resident arena is
reserved at startup. Static bookkeeping is about 256 KiB.

Use libnx's stack virtual-address region and reservation protocol, then map
the chunks with `svcMapMemory` to a contiguous RW alias. Source allocations
remain owned and cannot be freed while borrowed. FEX receives only the alias;
its accesses do not need a per-frame copy or guest ABI conversion. No graphics
or GPU buffer allocation is redirected through this path. Reference semantics:
[libnx memory syscalls](https://switchbrew.github.io/libnx/svc_8h.html) and
[libnx virtual-memory reservations](https://github.com/switchbrew/libnx/blob/master/nx/source/kernel/virtmem.c).
Local linked SDK behavior is exercised by the binary regression harness.

Allocate/map before publishing the pointer. Any failed allocation, reservation
or map rolls back completed work. If an unmap fails, retain the reservation and
all source allocations in quarantine. Release never passes a mapped alias to
libc `free`. Metadata locking never spans an allocation, map or unmap syscall.
The 64-MiB reserve and page fallback own different addresses and counters.

`SCRATCH_PAGES_V1` records attempts, recoveries, failures, held bytes/slots,
pieces, returns, map/unmap results, quarantine and capacity refusals. Existing
`SCRATCH_V3.failed` increments only when the fallback also fails. An allocator
failure event alone therefore does not imply final FEX failure. The crash
header identifies `high-scratch-pages-v1`.

## Validation and remaining uncertainty

Before packaging, require host tests with actual shared mappings and protected
source pages under ASan/UBSan, plus ARM64 execution of the linked old and new
scratch callbacks. The recorded 56-MiB live reserve + 16-MiB failed request
must fail on the previous ELF and succeed on the new ELF when small chunks
remain available. Test writes across the full alias, ownership under concurrent
requests, exhausted budgets, partial failures and unmap quarantine. Keep prior
controller, keyboard, Wine page storage, stack, scratch and fatal logging tests.

These tests model Horizon services; they do not run PES on Switch. Device
mapping availability and later HIGH workloads still need confirmation. A real
capacity shortage, virtual-address exhaustion or unrelated fault can still
fail, with separate telemetry rather than a claim of automatic recovery.

Keep renderer and clocks unchanged for the comparison. Exercise replay/events,
half-time, full-time/result and retain both logs before restarting. Interim
user-facing caution: HIGH remains experimental and may freeze due to runtime
memory allocation; MEDIUM is the reported stable option. Do not prescribe a
minimum RAM clock based on this capture.

Build with the pinned input-fix recipe plus `--scratch-pages`; package as a
folder without ZIP. Rollback restores the exact `high-thread-stack-v1` NRO.
