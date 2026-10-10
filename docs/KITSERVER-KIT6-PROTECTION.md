# Kit6: FEX guest protection round trip

The Kit5 device log reaches `rld.dll` successfully, then exits with a guest
write access violation. It is not the Kit4 early `c000001d` failure.

Evidence from the supplied Kit5 run:

- 4.447 s: page `0x01c80000` changes from `0x80` (execute/write-copy) to
  `0x20` (execute/read).
- 4.727 s: the same page changes `0x20 -> 0x40 -> 0x20`. The old protection
  observed by Wine is the read-only value.
- 4.898 s: a write to `0x01c80042` fails. Wine reports `vprot=0x25` and
  Horizon reports `perm=5`; both describe a committed readable/executable
  page without write permission.
- The FEX route reconstructs guest PC `0xf9b811ff`, RVA `0x211ff` in the
  loaded `rld.dll` at `0xf9b60000`. It does not report an SMC recovery.
- The process exits with `c0000005` around 4.986 s. `crash.log` records a
  nonzero guest exit, rather than an independently captured native fatal.

The NRO observer's caller address is a shared native syscall trampoline. It
does not independently identify whether each protection request came from
FEX or the guest. The causal attribution below combines the log sequence
with the delivered source and a reproduced failure, not that caller field.

## Reproduced mechanism

FEX MTRACK temporarily replaces writable executable page permissions with
read/execute. The local port removes writable tracking when the guest later
requests read/execute, which avoids retaining expensive SMC validation for
ordinary text after a loader finishes patching it.

However, `VirtualProtect` can expose the temporary MTRACK permission as the
old permission. A caller that saves that result, patches the page, and
restores it therefore restores RX rather than the logical writable
permission. The local RX demotion then forgets writable tracking. A later
write is neither permitted nor recovered by the SMC tracker.

This round trip is reproduced using the actual delivered tracker and
WOW64 protection notification code, a modeled NT API, and real Linux
`mmap`/`mprotect` permissions. Both ordinary writable executable pages and
image write-copy pages fail before the change and recover afterward.

The pinned [upstream FEX tracker](https://github.com/FEX-Emu/FEX/blob/e2f973fe931e6dc2ce523795e51ca1ac3ca85816/Source/Windows/Common/InvalidationTracker.cpp)
retains RWX intervals across RX notifications. Kit6 retains the local RX
demotion optimization and corrects the old-permission round trip instead.
Actual Kitserver success still needs a Switch test.

## Change

Before a guest protection call, the tracker examines only its first page,
because the NT API returns the old protection of that page. If that address
is tracked as writable and its current permission exactly matches the FEX
trap, FEX invalidates the page's compiled code and restores its writable
permission before the native call reads the old value.

The existing thread-creation lock and code-invalidation lock serialize the
pair of notifications. The code lock spans the native operation so another
compiler cannot reapply RX between restoring the permission and reading it.
Post-notification updates tracking without recursively taking that lock.

An explicit successful guest RX request still removes writable tracking.
Failure re-arms the temporary trap and preserves the guest error/output
contract. Guarded, inaccessible, and untracked pages are not untrapped.
No module name, game address, instruction bypass, or writable override is
used. FEX profiles, arithmetic settings, optimizer, JIT limits and renderer
remain unchanged. The fix runs on protection requests, not every frame.

## Validation and limits

- Delivered failure reproduced in the old source; candidate passes ten
  cases with ASan/UBSan and real host page permissions.
- Covers explicit RX, transient RWX text, image write-copy, failed API and
  query/untrap calls, invalid ranges, first-page boundaries, and a concurrent
  compiler attempting to re-arm the page during the call.
- Linked ARM64 allocation, SMC code emitter, profile getters, FPU conversion,
  timer and CRT checks pass. Module imports resolve against the supplied
  Wine runtime.
- The combined historical native/PE heap test has a native-side model gap:
  it only models malloc, while the unchanged Kit5 NRO also has page-store
  recovery. Its PE component passes independently. Existing Kit5 NRO
  receipts are retained; no claim is made that this legacy combined harness
  passed against the current NRO.
- The FEX candidate is built from the hash-verified delivered source and
  adapters. The toolchain is the Linux-hosted variant of the same pinned
  LLVM-MinGW release; the original module used its macOS-hosted variant.
- No Switch compatibility or performance result is claimed yet.

## Device package

The test overlay contains the unchanged Kit5 NRO and the new ARM64
`drive_c/windows/system32/libwow64fex.dll`. The launcher still displays
`0.3.9-kit5`; the module identifies itself with `[FEX-PROTECT] kit6 v1`.
Use Debug launch and return its runtime log; preserve a crash log if one is
written. Normal launch retains the Kit5 policy of no diagnostic SD writes.

Runtime Fixer is still pinned to the production module: Check runtime will
report this experimental `libwow64fex.dll` as changed, and Repair runtime
would restore the production module. The package includes a rollback copy.
The game executable, Kitserver files and both compared `rld.dll` files are
not changed or included in the overlay.
