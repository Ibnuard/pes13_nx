# Kit12: implement the missing CreatePipe path

The Kit11 device log SHA-256 is
`f2179410398deef557d90d3e8d78aed4591021fe127f29fa76941d2fdf5e855a`.
The user reports Exhibition -> controller-page freeze with audio continuing.

Kit11's VA partition is active (`guest_end=0x30000000`), with 722 MiB of early
reservations. The previous `c0000017` reservation/heap failure does not appear
in this run. Presentation continues, without proof of scene progress.

Starting in the 84.664-second sample, NT call 0x7f and server request 0x8e
dominate. Exact source tables identify **NtCreateNamedPipeFile** and
**create_named_pipe**. Recent results on thread 76 (`sysFileReadWriteThread`)
are `c0000002 / STATUS_NOT_IMPLEMENTED`. Samples after 89 seconds show about
415,000–417,000 requests per five seconds, sustained to the end at 129.708 s.

Wine's `dlls/kernelbase/sync.c:CreatePipe` uses access `0x80100100`, as logged,
and retries `NtCreateNamedPipeFile` until success. The embedded Horizon server
had no handler for request 142. Its generic unsupported reply therefore feeds
that retry loop. This is stronger evidence than a GPU stall or an unproven
memory hypothesis; progressing past the menu still needs a Switch test.

## Implemented scope

* Wine-generated `Win32.Pipes.*` anonymous pipes: synchronous, non-alertable,
  byte stream, single instance, inbound server and outbound client.
* Both NT namespace spellings resolve to the same pipe. Handles own real
  endpoints; duplicate handles retain their shared endpoint until last close.
* Bounded RAM ring, with condition waits for empty/full buffers, partial reads,
  buffered-data drain after writer close, broken-pipe errors and close wakeups.
* Active I/O owns an object reference. Last handle close wakes it without
  freeing the object while that operation is still running.
* ReadFile/WriteFile use normal Wine buffer validation and completion handling.
  PeekNamedPipe, pipe/local/access/mode/standard queries and GetFileType have
  pipe-specific handling instead of falling into the SD directory path.
* Unsupported message/overlapped/general named-pipe modes return errors. This
  is not a claim of a complete Windows named-pipe subsystem. Synchronous
  cancellation via a separate CancelSynchronousIo request is not implemented.

This changes the embedded Wine server and its NT file bridge. It does not
change FEX, clock scaling, renderer, presets or Kitserver/game binaries. The
Kit11 VA partition is retained. Normal launch remains without diagnostic files.
Debug creation records are bounded to twelve `ANON-PIPE` entries.

## Verification

The companion host test executes production pipe/server helpers with real
pthreads under ASan/UBSan. It covers wrap/full/empty, a 2-MiB transfer, partial
reads and non-consuming peek, close while blocked, duplicated handles, and
allocation-failure cleanup. Handle bootstrap and reply transport are modeled.

The ARM64 test executes the linked create/open, actual Wine read/write/query
wrappers, and actual handle duplicate/close code. OS locking/allocation,
buffer validation and reply/completion transport are modeled. Neither test
executes PES on a Switch or establishes long-match stability.

## Device check

Copy the package's `switch` folder to SD root, replacing the NRO and its exact
FEX DLL. Launch via the 32-bit no-alias NSP, using Debug launch and the same
Medium preset, renderer, clocks and plugins as Kit11. Try Exhibition ->
controller settings -> team selection -> kick-off. Retain the runtime log
even on success. If HOME still responds during a freeze, allow about fifteen
seconds of diagnostics and close via HOME -> X. Kit11 NRO rollback is included.

Success requires pipe creation/open and scene progress, not higher present
counts. The separate gameplay.dll attachment error is not repaired here.
