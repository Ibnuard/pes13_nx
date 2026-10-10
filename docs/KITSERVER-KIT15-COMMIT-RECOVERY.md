# Kit15: guest commit recovery

The Kit14 device run reached loading after game plan. At 146.808–147.999 seconds,
23 `MEM_COMMIT` requests failed with `c0000022`. Most requested `0x390000`
(3.5625 MiB). Some later allocations succeeded. At 148.266 seconds the main
guest called `NtTerminateProcess(self)` with exit code zero. The runtime parked
that thread; presents then stopped at 5,080. This was a guest exit, not evidence
that a Vulkan call remained in flight.

Kit14's sampled pipe counters confirm buffer reclamation and no pipe allocation
failures. The earlier pipe retry storm is absent. The global HMAP diagnostic
budget had already been consumed by startup mapping probes. Consequently this
log alone cannot establish whether the later backing failures were caused by
heap capacity, fragmentation, or kernel mapping rejection. It does not justify
requiring a higher RAM clock.

## Source defects addressed

- The old commit path removed the original reserved range before acquiring its
  backing. A failure then left a hole in the host mapping tree and libnx
  reservations. Retrying the same guest commit failed even after memory became
  available. Kit15 prepares replacement metadata, backing and permissions while
  retaining the original exclusion. Only a successful mapping replaces it.
- Backing allocations already hold the mapping mutex, so the external pressure
  callback cannot reacquire it. This path now directly releases only wholly idle
  backing arenas after an allocation fails, then retries before falling back to
  smaller pieces. Live and partially occupied arenas stay intact.
- `MEM-FAIL` has separate, rate-limited diagnostic budgets for backing,
  reservation, map, permission and commit failures. It records heap free space,
  untaken heap, the top free block, and spare/idle pool bytes. Kernel failures also
  record source/destination mapping metadata. These reports run only in Debug
  launch, allocate no additional buffers, and preserve the original errno.

No increase to the heap/VA limit, renderer change, FEX preset change, game/plugin
binary edit, or forced continuation after a failed allocation is included.
The guest VA partition and Kit14 pipe fix remain enabled.

## Validation and limits

`tests/fextendo_commit_binary.py` executes the actual old/new ARM64 code with
allocator and kernel services modeled. With injected backing, kernel-map and
reservation failures, Kit14 loses the reservation in three cases and cannot
retry. Kit15 preserves the original range and successfully retries all five
cases without an interval exposed to native allocators.

A separate budget test retains one idle 2 MiB arena and one partially occupied
arena. The old direct 3.5625 MiB request fails; Kit15 releases the idle arena and
succeeds, preserving the live bytes. The memory-observer test checks normal
launch silence, per-stage limits, status details, and errno preservation.
Input, startup, production logging, guest VA, section aliases, pipe I/O/lifetime,
directory handling, launcher UI and pool-pressure regressions are checked too.

These are verified runtime corrections, not proof that the console freeze is
resolved. This package still needs the same Kitserver workload on Switch. If it
fails again, the new log should distinguish the remaining allocation cause.

## Device test

Copy `switch/` onto the SD root, replacing the NRO and included FEX DLL. Keep the
same Medium preset, renderer, clocks and patch. Launch through the 32-bit no-alias
NSP using Debug launch; confirm version `0.3.9-kit15`. Proceed from Exhibition to
game plan, then kick-off. Return `fex-runtime.log`, including a successful run.
If the image stops and HOME responds, leave it for about 15 seconds before
closing. Normal Launch remains without diagnostic file writes. Rollback contains
the exact Kit14 NRO. No ZIP or game/plugin files are included.
