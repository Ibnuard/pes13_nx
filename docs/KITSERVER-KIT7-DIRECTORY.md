# Kit7: streaming Kitserver directory enumeration

The latest supplied run is actively enumerating Kitserver files at the end of
the log. It does not contain a captured terminal failure. `crash.log` contains
only its armed header, which cannot rule out a failure after logging stopped.

- Kit6's FEX protection marker is present, with successful protection repairs.
- At 12.367 seconds, handle `0x1c34` begins scanning
  `kitserver13/ISN PATCH 26/img/dt00_e.img/`.
- At 163.087 seconds, the same handle successfully returns
  `unnamed_14452.bin`, at enumeration index 4674.
- The sample rate falls from roughly 219 entries/second near the start to
  14 entries/second around indices 4000–4674.
- The corresponding PC directory contains 14,258 files. The Switch scan has
  not reached the end of that directory in the supplied log.

## Cause and change

The Horizon Wine server opens the directory for **every** query and reads from
the beginning until it passes the previously delivered index. Enumerating N
entries therefore repeats approximately N squared / 2 directory reads. It
also holds the shared server object mutex during those repeated scans.

Kit7 retains one `DIR` cursor per server file object, so ordinary queries resume
where the previous query stopped. Duplicate handles share that object under
the existing mutex. Independent directory objects retain separate cursors.

The pending name remains owned by the open cursor until the reply allocation
succeeds. Short buffers and allocation failures do not consume it. A changed
filter can reopen and seek from the last delivered index, preserving the
existing mask-change behavior; identical filters do not trigger a rescan.
Explicit restart, end of enumeration and final object destruction release
the cursor. End of enumeration remains sticky until restart or filter change.
Directory changes after EOF can be observed by restarting the search.
Filesystem read errors are propagated rather than treated as EOF.

This is a streaming change: no full directory snapshot, no name cache on SD,
no game-specific path filter and no removal of Kitserver files. Debug output
keeps initial entries, one progress record per 256 queries, restart and error
records instead of one line per successful file.

The NRO version is `0.3.9-kit7`, with marker:

```
[HZDIR] v2 persistent directory cursor; bounded trace
```

The package retains the exact Kit6 FEX module. Its protection fix and normal
optimizer remain enabled. Presets, DXVK and game binaries are unchanged.
Normal launch retains the existing no-diagnostic-write policy; Debug launch
records startup and errors as before.

## Validation

The host regression compiles the actual before/after directory handler with
ASan and UBSan, using real Linux directories and fault-injected server plumbing.
With 14,258 files plus the two synthetic dot entries:

| Operation | Before | Kit7 |
| --- | ---: | ---: |
| Open directory | 14,261 | 1 |
| Read directory | 101,695,188 | 14,261 |
| Trace records | 14,261 | 60 |
| Returned entries | 14,260 | 14,260 |

The ordered result hashes match. Tests also cover short replies, allocation
failures, open/read errors, wildcard filters, mask changes, restart, independent
objects, duplicate handles, concurrent queries, and cleanup. These operation
counts demonstrate removal of the repeated scan; they are not Switch timing
measurements or a promise of a proportional improvement in total startup time.

Linked ARM64 and packaging receipts accompany the delivered build. Host tests
model the server transport and OS services; they do not run PES or Horizon's
SD implementation. Device launch with this patch still needs user validation.

## Install and rollback

Copy the complete `switch/` folder to SD. It contains the new NRO and the Kit6
FEX module. Use the existing 32-bit no-alias NSP and Debug launch for the test.
Do not run Runtime Fixer's Repair during this experiment: its production
catalog still restores the old FEX module. Check runtime may report the
experimental module as changed.

`rollback/switch/` restores the previous NRO. The FEX module is identical in
Kit6 and Kit7, so the rollback does not replace it. No ZIP or game/patch files
are included.
