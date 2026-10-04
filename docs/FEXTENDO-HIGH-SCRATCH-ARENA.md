# HIGH scratch arena v2 candidate

The latest on-device freeze is another FEX compiler workspace allocation
failure, now for **16 MiB**. The first reserve helped service 8-MiB requests but
could not combine its separate allocations. This candidate keeps the same
32-MiB ceiling and replaces those separate buffers with one contiguous arena.
Console validation is still required.

## Evidence and scope

Input `transition.log` SHA-256:
`4415037f5358afa0d3a582c36b729e0313466ed51097ac86898aa075e345fff7`.
Private evidence is under `local/high-freeze-review/4415037f5358/`.
The accompanying previous log is the earlier 8-MiB failure, SHA-256
`3d0a8941969b1d508a2c418d8a40efb854270e904730b08fb9b0706f72020d03`;
it is not a second reproduction on the reserve build.

At trace sample 229,228 ms, events are 168 ms old, placing the failure around
229,060 ms (3:49 on this log's clock):

```
EVENT kind=3 code=00000005 thread=81ff detail=16777216 address=1000
[FEX2-HEAP] STOP compiler scratch failed bytes=0x0000000001000000
[EXC] ... pc=0xff68bb88 ...
[EXC] unhandled status=0x80000003; parking thread
```

This is a failed page-aligned 16-MiB allocation followed by the same fatal FEX
helper (DLL base `ff540000`, RVA `14bb88`). Presentation stops at 11,732 calls and
remains there for the last 16 seconds. Unlike the previous run, the trace no
longer shows frames continuing after the fatal event.

Immediately before the failure, the reserve reports four initialized slots,
zero busy, eight acquisitions and eight returns. Its one 8-MiB fallback
succeeded. Thus 32 MiB was sitting idle, but the v1 reserve's four independent
allocations cannot satisfy one contiguous 16-MiB request. The old `failed=0`
counter covered only 8-MiB requests; the allocator event and fatal message
capture the 16-MiB failure that counter missed.

Nearby aggregate free memory is 142,197,872 bytes (about 135.61 MiB), including
9,023,488 bytes of untaken heap. Aggregate free bytes are not a contiguous-block
guarantee. An earlier 6,225,920-byte `memalign` failure occurs around 104,838 ms;
the game continues afterward. This candidate targets the later confirmed fatal
scratch request, not every allocation failure or the separate startup mapping
fault found in an earlier run.

## Implementation

At native FEX bootstrap, request one page-aligned 32-MiB allocation. If that is
unavailable, try a contiguous 16-MiB then 8-MiB arena, stopping after the first
success. No allocation failure is hidden from the ordinary fallback path.

The host scratch callbacks manage this arena in 8-MiB units. Requests between
8 and 32 MiB receive enough consecutive units; live ranges have exclusive
ownership and never move. When a range is explicitly released, its adjacent
free units become usable by a larger request. A 16-MiB request can therefore
use two released units, and a fully idle arena can serve 32 MiB.

Requests smaller than 8 MiB or larger than 32 MiB retain normal aligned
allocation. If there is no sufficiently large consecutive free range, use the
normal allocator and return its real result. General FEX heap, guarded data,
guest mappings, JIT executable mappings, and the frozen DLL stay unchanged.
No libc allocation or free runs while holding the arena mutex.

Interior, unaligned, and already returned arena pointers cannot release a live
range or reach libc `free`; they increment `invalid_release` for diagnosis.
The caller contract still requires exactly one release of an allocation base.
The allocator cannot make use-after-free or stale-pointer callers valid.

The arena remains a maximum 32-MiB reservation. It reduces general free memory
while idle and can itself fragment around live allocations; it cannot compact
live compiler data. More than 32 MiB of concurrent workspace may still require
fallback and may still fail. This addresses the observed idle-reserve growth
case without increasing the previous build's memory budget.

## Build, evidence and tests

The production runtime lock and FEX DLL are unchanged. DLL SHA-256 remains
`17dcf3e78371a717a9c41da5bffa4d6a5755d6479afa0a8ade12abcc7639ad23`.
Only the copied frozen native adapter's four integration anchors plus the
project-owned scratch header change. Source hashes, local native dependency
differences and test results are included in `evidence`.

ASan/UBSan host tests exercise full, partial and absent arenas, 8-to-16/24/32-MiB
growth under allocation pressure, mixed concurrent sizes, nonadjacent holes,
ownership and general heap cross-thread frees. Linked ARM64 tests execute the
actual host ABI table and callbacks while modeling libc and Horizon mutexes.
The same simulated sequence is run against the previous NRO's companion ELF:
four 8-MiB claims, four returns, then a 16-MiB claim while ordinary allocation
is denied. It must fail on v1 and succeed on v2. This is a targeted regression
test, not proof of hardware memory behavior or PES performance.

Controller, keyboard, silent logging, diagnostics and Vulkan wrapper checks
also run against the new build. No game timing, frame cap, DXVK, replay quality
or graphics preset is changed in this candidate.

## Device test

1. Close PES through HOME, X, Close. Copy `switch` from this package to the SD
   root and overwrite the two matching files.
2. Test HIGH + Default DXVK with the same fixed clocks. Play around 10 minutes
   and trigger repeated ball-out/replay, corner and goal transitions.
3. Send `switch/pes13-fex/transition.log` even if the game does not freeze. If it
   freezes, wait about 10 seconds if possible before closing. Preserve
   `transition.previous.log` too when performing two runs.

The log retains `TRACE_V3` and now includes **`SCRATCH_V2`**: capacity, occupied
bytes, live allocations, hit counts by size, ordinary allocation failures for
all scratch sizes, largest free range, largest requested size and last failed
size. Logging stays on the existing two-second worker, bounded to 20 minutes.

Remove `launcher/diagnostics.txt` to disable tracing. To undo the arena change,
copy `rollback/switch` to the SD root: it restores the prior four-slot reserve
NRO (SHA-256 `d2f6417dc48d498eb3418e60953f2d813d87b2e35b7521edabb6b2c1b4340c8f`).
Disabling tracing does not disable the arena.

The package preserves the compact keyboard, grouped settings and input fix.
It is a targeted stability candidate, not a verified HIGH fix or an FPS boost.
