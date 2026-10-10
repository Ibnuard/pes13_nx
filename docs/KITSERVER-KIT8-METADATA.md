# Kit8: SD directory metadata and bounded startup observations

The supplied Kit7 log ends at 154.770 seconds. It contains no terminal exception,
allocation failure or process exit. The user reports a full-console hang: HOME
also stops responding. The log does not establish the cause of that hang.
An adjacent crash.log predates this run and is not evidence for its cause.

Kitserver is enumerating `ISN PATCH 26/img/dt00_e.img`. The cursor advances to
entry 4,096 at 32.679 seconds, then to 5,632 at 147.710 seconds, without a directory
error. The actual folder contains 14,258 files. JIT compile totals remain
unchanged during that interval. This identifies slow directory processing
during the observed portion, not a proven explanation for the eventual hang.

Kit7 removed repeated server-side enumeration. Its client still calls lstat for
each name. The linked libnx implementation gets the entry type, opens the file,
gets its size, closes it, reads timestamps and converts valid timestamps using
the time service. That repeats SD path lookups after enumeration already read
the file type and size.

## Changes

- The native server reply carries an optional regular-file size from the current
  libnx directory batch. The server and client are compiled into one ELF; PE
  DLLs and external Wine protocols are not changed.
- Only the mounted `sdmc:` fsdev device is eligible. Device identity, state size,
  magic, batch bounds, exact name, type and nonnegative size are checked.
- The client uses one real timestamp lookup, preserving the same timezone
  conversion, invalid-timestamp behavior, permissions and link count as fsdev.
  Wine's hidden-file, extended-attribute, reparse and result-layout processing
  still runs. Missing/failed hints or timestamp requests fall back to the original
  lstat path. Directory entries and synthetic dots keep that original path.
- File size is an enumeration snapshot, as with ordinary directory listings.
  A concurrently resized file can change after enumeration. No file data is
  cached and no metadata is written to SD.
- Debug launch records aggregate `[HZDIR-COST]` durations for the directory
  request, path construction, metadata, timestamp and timezone stages. Up to 16
  concurrent queries are observed; excess observers are skipped without delay.
  A pending stage over 500 ms is reported every five seconds by the existing
  maintenance thread. No new thread, suspend operation, timeout, cancellation or
  filesystem operation is introduced by the observer.
- Normal launch performs no diagnostic recording. FEX Kit6, normal FEX
  optimization, performance presets, renderer, game and patch files are retained.

## Validation and limits

The metadata host test uses the actual implementation with only SDK boundaries
substituted. It covers malformed/unsupported hints, real/invalid timestamps,
timezone-service failure, metadata lookup failures, quiet mode, observer capacity,
pending-stage reports and 2,000 concurrent observer operations under ASan/UBSan.
The real-directory handler test verifies the new reply layout and pending-entry
retries against 14,258 files, including duplicate handles and IO failures.

The package also requires the established ARM64 binary checks for production
policy, startup, input, keyboard, process parameters, FEX flag control and memory
fixes. Per-file test receipts and source/build hashes are included in the package.

No Switch test of Kit8 has been performed here. It reduces identifiable repeated
work; it does not establish that the system-wide hang is fixed. Timestamps still
require a path lookup. A kernel or filesystem hang can prevent even the existing
log writer from saving the final observation. A missing fatal record is not proof
that no fatal condition occurred.

## Device test

Copy the two files under `switch/` onto the SD root and use the NSP 32-bit
no-alias launcher. Use Debug launch once and retain that run's fex-runtime.log.
Look for version `0.3.9-kit8`, `[HZDIR] v3` and `[FEX-PROTECT] kit6`.
The `fast` counter should increase for regular SD files; stage costs distinguish
remaining filesystem work from server waits. If it hangs while HOME still works,
close normally. Do not keep waiting once the console itself stops responding.

Runtime Fixer Repair restores the released FEX module; reapply both overlay files
if Repair was used. The included rollback NRO restores Kit7, with the same Kit6
FEX DLL. No ZIP or game/patch binaries are included.
