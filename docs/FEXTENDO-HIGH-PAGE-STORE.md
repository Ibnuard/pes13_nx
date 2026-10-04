# HIGH full-time transition: fragmented Wine backing storage

Candidate: `high-page-store-v1`. This is a device-test candidate, not a promoted
production runtime. The frozen FEX DLL, DXVK, graphics presets and game timing
are unchanged. The previous 64 MiB FEX compiler reserve is retained.

## Reproduction and evidence

Input `transition.log` SHA-256:
`5c51467cdb44fa96972c41e8666d05259d68513b32e49f4eeac15af5be8a095d`.
It identifies the tested scratch64 NRO by build ID
`fe92e76a0211bfaad0e46ba428251ec968400eaf000000000000000000000000`.
The user reported that full time froze at approximately 8:40 after opening the
application. The trace begins 18.160 seconds after the crash session bootstrap.

The log contains three failed 16 MiB `memalign(4096, size)` requests at trace
510.179, 526.502 and 528.859 seconds, inside
`horizon_server_handle_create_mapping`. There are eleven failed 5 MiB requests
at 524.819–524.820 seconds inside `map_backing_at_locked`. These correspond to
approximately 8:48–9:07 after the session bootstrap. The heap still has roughly
131 MiB free in total. This is consistent with fragmentation, rather than total
exhaustion; the log does not measure the allocator's largest available block.

The renderer continues presenting roughly 55–58 times per second near the end.
That is presentation activity, **not** evidence that the match simulation is
advancing. There is no fatal record in `crash.log`, no FEX STOP, and the FEX
scratch counters show zero failed requests. Enlarging that reserve again would
not address these two Wine allocation sites. The exact effect of the allocation
failures on PES's result-screen state still needs a console reproduction.

## Change

Wine first uses its original contiguous allocation path. If that fails, the
backing storage is assembled from page-aligned pieces of at most 1 MiB. If a
piece cannot be allocated, the request shrinks down to 4 KiB. An allocation is
bounded to 4096 pieces; partial allocation failure releases all pieces and
returns `ENOMEM`. There is no additional startup reserve or larger process
memory limit.

For ordinary Wine mappings, pieces are mapped at adjacent guest addresses.
Offsets, file reads, EOF zero-fill, shared writeback, split unmaps and permission
changes are handled per piece. A failed operation rolls back completed pieces.
If the kernel refuses rollback, the backing and reservation are retained so
still-mapped physical memory is never handed back to the allocator.

Anonymous Windows sections use the same storage fallback. Their existing
anchors are bounded to individual pieces. Multiple views and descriptor I/O
continue to observe the same pages, including data that crosses piece boundaries.
`SEC_RESERVE` commitment bookkeeping is retained.

The opt-in diagnostic worker adds `PAGES_V1` counters: recovered allocations and
bytes, live split bytes and pieces, final failures, rollback failures, peak live
bytes and released allocations. A failed large `ALLOC_SITE` can now be followed
by successful recovery; evaluate it together with `PAGES_V1`, rather than treating
every initial `memalign` failure as fatal. Counters are sampled without taking
the memory allocator or mapping locks.

## Validation and limits

- Host ASan/UBSan tests reproduce the original 16 MiB section failure with a
  fragmented allocator and verify the fallback using real Linux shared mappings.
  Tests cover two views, cross-piece read/write coherence, commitment metadata,
  partial unmaps, allocation exhaustion, anchor failure and failed rollback.
- ARM64 tests execute both failing Wine call sites from the previous NRO's ELF
  and the candidate ELF with the same modeled allocator. The old binary fails
  both requests; the candidate maps the 5 MiB backing and returns success for
  the 16 MiB anonymous section. Kernel failure cleanup and quarantine are tested.
- Existing native controller, keyboard, overlay, logging, crash, live snapshot,
  scratch allocation and source-integrity checks are retained.

The host's OS and modeled Horizon calls do not certify kernel behavior, PES
gameplay or HIGH stability. Additional mapping calls and metadata occur only
on fallback; overhead on a fragmented Switch heap has not been measured. The
4096-piece limit and true memory exhaustion still return allocation failure.
Rollback failure deliberately retains memory, recorded by `rollback_failed`.

## Device test

Copy only the package's `switch` folder, replacing the NRO and diagnostic marker.
Use the same HIGH preset, renderer and clocks as the last test. Play through
half time, full time into the result screen, then begin another match if possible.
Save `transition.log` and `crash.log` before relaunching. If the match freezes,
leave it for approximately 15–20 seconds before closing and note the elapsed
time and event. Include previous logs if a second launch occurred.

The package's rollback NRO is exactly the scratch64 build that produced this
input log. Removing `launcher/diagnostics.txt` disables periodic trace and
thread snapshots, but leaves the memory fallback and direct crash writer active.
