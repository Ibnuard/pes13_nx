# Kit9: remove unused per-file timestamp IPC from the AFS2FS name index

The user confirms Kit8 froze during blackscreen/initial loading, before the menu
or match, and required a hard restart. The input log is from
`Pictures/pesnx/SS/SS/fex-runtime.log`, not the prior `SS/fex-runtime.log`.
It ends at 85.240 seconds while listing entry 6,400 of `dt00_e.img`.
No terminal exception, allocation failure or exit is recorded. A system-wide
hang cannot be ruled out merely because its cause was not flushed to the log.

## Measured bottleneck

At 81.868 seconds the directory observer reports:

| Phase | Accumulated duration |
| --- | ---: |
| Timestamp lookup | 66,978 ms |
| Server directory request | 1,107 ms |
| Timezone conversion | 920 ms |
| Other metadata | 661 ms |
| Path construction | 60 ms |

Between the 20.422 and 81.868 snapshots, timestamp requests account for
60,659 of the 61,446 elapsed milliseconds (98.7%). Only one directory query is
active in those snapshots. This locates the prolonged startup work. It does
not prove that timestamp IPC is the cause of HOME becoming unresponsive.

## Consumer verification

The supplied `afs2fs.dll` is version 13.4, SHA-256
`d5f6cfa5438978c0ba57310fff67e1a7a8d167beffc93bee3cc6cc8dd4560c26`.
A read-only audit of its inner file enumeration loop finds direct access to
WIN32_FIND_DATA's attributes (offset 0) and filename (offset 44), and no direct
access to timestamp fields (offsets 4..27). The name pointers are used for
BIN-ID parsing, length validation and copying into the index. The full Find
buffer is passed back to FindNextFile for the next result.

This agrees with the [AFS2FS source's InitializeFileNameCache](https://github.com/NiklasOff/kitserver/blob/main/src/afs2fs/afs2fs.cpp#L229).
The ProgramData read attempt is a search for the base IMG header to size the
index; it is not a failed write of an index cache. No patch DLL or game file is
changed or redistributed.

## Scoped compatibility behavior

With `kitserver_fast_scan=1` (the Kit9 default), regular files immediately under
`sdmc:/.../kitserver[digits]/.../img/<archive>.img/` use the native directory
batch's type and size. The runtime omits date lookups for these directory
results only. Their four directory time fields are explicitly returned as zero
(unavailable), not as fabricated current dates. Names and Wine attributes remain
intact. File contents, direct file-information/time queries, ordinary folder
listings, directories and GDB/config/save files retain their existing behavior.

The path check rejects parent traversal, empty components, lookalike Kitserver
names, nested directories below the IMG folder and non-SD devices. Invalid
metadata hints retain the original lookup. File size remains an enumeration
snapshot; changing/deleting files during enumeration is not an atomic operation.

The compatibility policy is based on the inspected AFS2FS consumer. A different
patch component that relies on directory-result timestamps may need it disabled:

```ini
[compatibility]
kitserver_fast_scan=0
```

Add this to the existing configuration.ini; no extra marker file or launcher
setting is required. This restores Kit8's timestamp behavior without changing
FEX or the renderer. The included Kit8 NRO also provides a full rollback.

## Validation

- Actual metadata C under ASan/UBSan: 14,258 distinct asset entries perform zero
  path/timestamp/timezone service calls; boundary checks and the override pass.
- Linked ARM64 helper: eligible entries perform no SD/file-open/directory/time
  IPC, preserve 64-bit size and caller guards, and restore fallback when disabled.
- Actual directory-handler test: all names/order, pending retries, masks,
  duplicated/concurrent handles, cleanup and IO errors remain correct.
- Existing production/startup/input/keyboard/process-parameter/FEX-flag/memory
  checks are required by the package builder, with source and ELF hash receipts.

Normal launch stays free of diagnostic logging. Debug launch retains bounded
cost observations and adds `asset_names` to verify use of the new path.
The startup marker is `[HZDIR] v4 asset_scan=1`. Native dependencies, FEX Kit6,
performance presets, renderer and game/Kitserver binaries are preserved.

No Kit9 hardware test has been run here. Removing the measured repeated work is
verified locally; actual startup time and resolution of the full-console hang
must be evaluated on Switch. If HOME stops responding, there is no value in
leaving the console frozen for additional diagnostic minutes.
