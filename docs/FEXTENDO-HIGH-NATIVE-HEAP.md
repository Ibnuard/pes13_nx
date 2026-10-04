# Native Rust CPU heap recovery and fatal context

## Full-match checkpoint

The user reports that `high-native-heap-v1` completed a full 90-minute match
(in-game time). This is the first reported full-match success for this
candidate and the checkpoint requested after that test. It does not mean
90 minutes of wall-clock testing. No new diagnostic files or FPS measurements
accompanied the confirmation, so the exact cause of the earlier Rust abort
remains an inference rather than a newly captured allocation failure.

The source and build scripts were checked against the tested build receipt;
all 23 local validation receipts passed. The tested artifact is:

- Package: `dist/pes13-fextendo-high-native-heap-v1`
- NRO SHA-256: `cea8c64fb6a7749796d9a2365d2df8729cb5a1d4a77a52fb38dda5d204908279`
- ELF SHA-256: `3ce0de2e37598404bc03424f0bf2de3c0353c6114a1ff0bc88733527a484ec22`
- NRO build ID: `2e40eeaa1e0af518357b5a2ff0a5c4e0ea6071ad000000000000000000000000`

The immutable local package/receipts retain their original pre-device-test
status; this note records the subsequent user result. This source checkpoint
also retains grouped launcher settings, compact keyboard/shortcut controls,
and the controller-input fix used by the tested candidate. Generated builds,
game files, saves and logs remain local. The production runtime lock is not
promoted by this checkpoint.

## Evidence and uncertainty

Archive `local/high-freeze-review/2c74974df7c2` matches the delivered
`high-fragmented-heap-v1` NRO by build ID. At **113437 ms**, thread `2a01c0`
records `NATIVE_ABORT`. The caller offset is `0x87c8c`; this is a **return
address**. The call instruction at `caller - 4`, `0x87c88`, belongs to
`std::sys::pal::unix::abort_internal`. Looking up the return PC without
subtracting four incorrectly names the next function, `small_c_string`.

This capture does not include a FEX STOP. The last sample is 629 ms before
the abort: 4148 presents, no present errors, about 66.16 MiB total native
heap free. Fragmented lookup recovery succeeded once for 1 MiB, then
released it: `SCRATCH_PAGES_V1 recovered=1 returned=1 held_bytes=0`.
Wine backing recovered five allocations and the stack reserve recovered one.
These on-device results verify those fallback paths were used, but do not
establish a clean run or a solution for every native allocation.

The linked Rust runtime is from Mesa's NAK shader compiler. Rust allocation
failure and panic both can reach this abort function. The previous fatal
record omitted the call chain and buffered stderr, so **the root cause of
this native Rust abort is not yet proven**. Native heap fragmentation is a
testable explanation, not a conclusion that the shader compiler exhausted
all physical RAM. Do not call this an established NAK OOM or a GPU crash.

## Candidate

Extend the same bounded CPU page store to native Rust's four allocation
operations. Normal allocation remains the first attempt. On failure, use
page fragments down to 4 KiB in a contiguous virtual CPU buffer. FEX and
Rust share the existing 128-MiB / 128-owner limits; no new resident reserve
or per-frame copy is added. Ownership is held in static metadata, including
the aligned user address; never probe a header before a foreign malloc
pointer. Ordinary heap pointers outside the alias range bypass its lock.

Rust `alloc_zeroed` zeros the fallback buffer. Realloc preserves the common
prefix on success, releases through the correct owner, and leaves the old
allocation unchanged on failure. A fallback allocation can later move back
to an ordinary native heap allocation. Partial mapping failures roll back;
failed unmaps keep sources/reservations quarantined.

This is limited to Rust **CPU data**. Native NAK returns CPU shader bytes;
NVK copies them into its separately allocated GPU upload buffer in
`nvk_shader.c`. The GPU buffer allocator and executable FEX JIT mappings
do not use this generic RW page alias. Generalizing to every libc/GPU
allocation would violate their distinct mapping requirements.

The four Rust ABI entry points are reviewed against the unchanged, pinned
`libnak_rs.a`, SHA-256
`f56fc46711c90330a9d68ff78cf00fd31a2525f922b6a90b77366d044542381f`.
The builder refuses an unreviewed archive rather than guessing new mangled
symbols or an internal Rust ABI. Linker wrappers call the original shims
via `__real_`; they do not mutate the Mesa archive. The binary regression
checks every direct call to these four entry points and executes the real
ARM64 allocation shims plus fallback implementation. All installed native
library hashes remain unchanged from the previous candidate.

Allocator contracts follow the [Rust GlobalAlloc documentation](https://doc.rust-lang.org/std/alloc/trait.GlobalAlloc.html):
alignment, initialized zeroed storage, realloc prefix preservation and
ownership retention on allocation failure are required. No allocator
unwind or recursive Rust allocation is introduced.

## Fatal evidence

The primary abort record is flushed first. A separate `NATIVE_CONTEXT`
record then includes up to 12 frame-chain return PCs, the latest buffered
512 bytes of native output and a pending allocation failure for that thread.
Frame reads are bounded to the current readable mapping, require alignment
and monotonic progress, and stop on a cycle/out-of-range pointer. This is
best-effort evidence, not a complete unwinder. Trace locking is try-only;
formatting uses static storage and cannot recursively allocate.

Unrecoverable Rust requests directly record `RUST_ALLOCATION_FAILED` with
operation, requested size, alignment, previous size and caller before
returning failure normally. The record alone does not prove termination:
Rust fallible-allocation callers may handle it. A later abort/exception is
separate evidence. `RUST_HEAP_V1` counts fallback activity every two seconds;
normal allocations have no per-allocation logging/counter increment.

## Verification and device test

Retain the 21 previous checks and add Rust heap host/ARM64 tests. Host tests
use real shared mappings with ASan/UBSan, concurrent owners, native/fallback
transfers, alignment through 2 MiB, failure preserving old bytes, rollback
and quarantine. ARM64 checks use the unchanged original Rust shims and
modeled libc/kernel services, including virtual aliases above 4 GiB.
The modeled fragmented allocation failure is a regression scenario; it
does not reproduce the full on-device crash or establish its root cause.

The fatal-file checks cover direct flush, checked/cyclic/unreadable frame
chains, buffered text, contended diagnostics, allocation layout, rotation,
record limit and unchanged termination semantics. Input, keyboard, silent
I/O, Wine/FEX memory and native-stack checks remain required.

Deliver only NRO and diagnostics opt-in under `switch/`, as a folder.
`rollback/` contains the exact prior high-fragmented-heap-v1 NRO. Keep HIGH,
renderer and clocks constant, replay transitions through full-time/result
and preferably a second match. Preserve both logs before reopening. Check
`RUST_HEAP_V1` recovery, returned/shared live bytes, and new fatal context.
The user-reported full-match result is recorded above. Repeated matches and
other device/renderer combinations still need coverage; this is not a claim
of measured 60 FPS or universal HIGH stability.

## Rebuilding this checkpoint

Use the existing pinned keyboard-v4 archive, Wine source tar and local
WSL SDK/Mesa dependencies. The candidate was built with:

```sh
python3 tools/build-fextendo-input-fix.py \
  --archive local/production-input-fix/fextendo-runtime-keyboard-v4.zip \
  --wine local/production-input-fix/wine-source.tar.gz \
  --output /home/blekjek/pes13-build/production-input-fix \
  --build-root /home/blekjek/pes13-build --jobs 4 \
  --transition-trace --scratch-reserve --scratch-reserve-mib 64 \
  --crash-log --live-freeze --page-store --thread-stack-reserve \
  --scratch-pages --rust-heap
```
