# Kit14: release storage when the last pipe reader closes

The supplied Kit13 device log has SHA-256
`1d1a9af3125b9b75e9926940d53e8b3b36dab74e8f04541edeaf37b2467cb3da`.
It uses Medium 720p, DXVK 3.1.1, and the 32-bit no-alias launcher.

## Device evidence

The Kit13 fix works on-device: at 80.277 seconds, the 2,101,740-byte pipe accepts
the entire 1,050,870-byte BIN. Reads consume it, including the final 2,294 bytes
that previously could not be written. The user reaches team selection.

At 118.081 seconds the probe starts sampling `STATUS_NO_MEMORY` (`c0000017`)
from NtCreateNamedPipe (0x7f) / server create_named_pipe (0x8e). At the end,
roughly 395,600 requests repeat per five seconds. The asset-loading guest and
its server worker consume about 3,022 and 1,700 ms of CPU per 5,010 ms.
Presentation stops at 3,347 frames; no new frame is seen for the last 15 seconds.
This is an allocation-failure retry loop, not evidence of a Vulkan call stuck
in flight. It does not establish the cause of every earlier slow team change.

## Storage-lifetime mismatch

Kit13 used one allocation for the pipe object and its entire quota. Closing the
last reader merely set `read_open=0`; all data remained until the writer also
closed. That retains multi-MiB buffers even though no read can ever access them.

[Kitserver's producers](https://github.com/NiklasOff/kitserver/blob/4077d5ab1fa82c6f698d947e44bdd76d4dc06b27/src/kserv/kserv.cpp#L1833)
return a read handle after writing the BIN; their success paths leave the write
handle open. [AFSIO replaces old read handles](https://github.com/NiklasOff/kitserver/blob/4077d5ab1fa82c6f698d947e44bdd76d4dc06b27/src/afsio/afsio.cpp#L339)
and closes them when reads finish. The supplied kserv DLL's three producers
match the already audited serial handoff; no plugin binary is modified.

For comparison, [Wine's pipe endpoint destruction](https://github.com/wine-mirror/wine/blob/master/server/named_pipe.c)
disconnects the endpoint and clears its queued messages. The surviving handle
and the unobservable queued payload need not share a lifetime.

The device log only recorded the first 12 creates and did not record reader
closes or live buffer bytes. Therefore, retained pipe storage is a reproduced
runtime defect consistent with the device failure, not a measured accounting
of all memory used by the device. New counters allow that follow-up.

## Change and safety of lifetime

* Store the buffer separately from the small pipe object; keep the requested
  quota intact. Allocate bytes without zeroing: only the written `used` range
  is exposed through read/peek.
* Release storage when the final reader closes, including unread abandoned
  BINs. Duplicate readers retain it until their final close.
* Preserve a remaining writer handle and return broken pipe on subsequent
  writes. Do not forcibly close guest handles. Small handle metadata lives
  until its proper close; Kit14 does not fix a plugin's leaked handle itself.
* Serialize reclamation with the existing pipe mutex. Pending I/O retains its
  object reference and is awakened with the existing closed-end status.
* Closing only the writer preserves buffered data for the reader to drain.
  Allocation/lock initialization failures unwind without retained storage.
* Debug-only bounded ANON-PIPE v3 and ANON-MEM v1 records show live/peak storage,
  reclaimed bytes, and metadata/buffer/synchronization creation failures.

No extra worker, sleep, SD spill, heap-size increase, game patch, or FEX/DXVK
policy change is introduced. Normal launch retains its diagnostic-file gate.

## Tests

With an injected 8-MiB allocator budget, real pthread/pipe code under ASan/UBSan
reproduces Kit13's exhaustion after three retained writers (6,305,724 bytes
held). Kit14 completes 1,200 create/write/read-or-abandon/reader-close cycles
with all writers still open. Peak storage is 2,312,940 bytes; only 211,200 bytes
of pipe-object metadata remain until writer cleanup, which returns it all.

The actual old/new ARM64 handlers also reproduce the difference: the Kit13
binary hits no-memory after three cycles; Kit14 completes 36 cycles, retains
25,920 bytes of handle/object metadata, and releases everything at final close.
This test models OS allocation/locks and transport; it executes the real
create, duplicate, close, NtWriteFile and NtReadFile paths. Duplicate-reader data,
broken-writer status, byte integrity and allocation rollback are checked.

The prior Kit12 serial-write deadlock regression still passes with full quotas.
Existing close-wakeup, stream, production logging, startup, input, memory and
UI checks also pass or retain source-verified receipts for unchanged components.

This is not a Switch game test or an FPS guarantee. Repeated team changes,
kick-off and later transitions still need a device run. Use Debug launch with
the same configuration as Kit13 and retain fex-runtime.log. The package has
Kit13 NRO rollback and the same hash-verified FEX DLL.
