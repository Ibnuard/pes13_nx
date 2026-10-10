# Kit13: preserve the anonymous pipe's requested quota

The Kit12 device log has SHA-256
`a1408eb056bb5567ea136ada1b7ed3d76a655e39186fbcabcc9f5580fd2846bc`.
The user still reports the Exhibition-to-controller stall with uninterrupted audio.

At 76.711 seconds, pipe creation succeeds with a request for 2,101,740 bytes.
The previous create_named_pipe / c0000002 storm is gone. Thread 76,
`sysFileReadWriteThread`, instead remains inside **NtWriteFile (0x8)** on handle
`ab84`; its observed wait grows from 1.836 to 21.875 seconds. Frame presentation
continues, but that does not establish progress of the loading scene.

Kit12 silently limited the requested buffer to **1,048,576 bytes**. That was an
incompatible choice in our runtime implementation. Its concurrent stream test
had a reader available and therefore did not reproduce the Kitserver handoff.

## Source and supplied-binary confirmation

[Kitserver's kit, font and number BIN producers](https://github.com/NiklasOff/kitserver/blob/4077d5ab1fa82c6f698d947e44bdd76d4dc06b27/src/kserv/kserv.cpp#L1833)
request twice the packed BIN size, write the BIN synchronously, and only then
publish its read handle. The supplied `kserv.dll`, SHA-256
`06a6fea90a0c4eedba6e2b3d205052f2f273cb9a7427fd01b66416efb4a31123`,
has the same pattern at CreatePipe RVAs `b39a`, `ba2d`, `c0fd`. Read-only
Capstone checks verify the doubled quota, original write length and subsequent
read-handle publication. No game/plugin binary is changed or included.

For the observed quota, this pattern implies a 1,050,870-byte BIN: just
2,294 bytes larger than Kit12's artificial cap. The writer cannot finish, and
the function has not yet returned the read handle to PES. This agrees with
[documented synchronous pipe behavior](https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-createpipe):
a full buffer can block the write until a reader makes room. The runtime log
does not contain the caller PC or write length, so identifying this exact BIN
producer remains an inference supported by the quota, binary and reproduction.

## Change

* Honor every nonzero requested quota, with checked allocation size; retain the
  4-KiB default for a zero request. Allocation failure remains a real error,
  without silently returning a smaller successful pipe.
* Keep normal byte-stream capacity limits, backpressure, partial reads and close
  wakeups. There is no unbounded automatic growth or SD-backed spill file.
* Calculate circular indices without overflowing their unsigned DWORD range.
* Debug-only bounded records show requested/actual quota and the first 24 I/O
  begin/end pairs. This lets the next log confirm write completion and reads.

FEX, DXVK, configuration, presets and game/plugin files retain the Kit12 state.
The independent gameplay.dll attachment failure is still present in this log
and is not claimed fixed by the quota change.

## Validation

A real pthread test under ASan/UBSan reproduces Kit12's blocked writer using the
observed quota and inferred payload, with **no concurrent reader**. The new core
completes that handoff before reading begins. Eight candidate cases cover
default/near-1-MiB/exact-device/above-8-MiB quotas, full-buffer writes, wrap, data
integrity, close/drain, allocation failure and unsigned boundary arithmetic.

The ARM64 comparison executes the actual old/new NtWriteFile path. Kit12 reaches
the wait after copying 1,048,576 bytes. Kit13 completes the write, then a separate
NtReadFile returns all bytes intact, and final handle close releases allocations.
OS locks/allocation and transport are modeled in that test; the companion host
test uses real pthread scheduling. Existing production, input, memory and pipe
regression checks remain required by the packaging tool.

These tests do not execute PES on Switch. Controller-page progress, later asset
loads and match stability still need a device run.

## Device check

Copy the package's `switch/` folder to SD root, merging with `SD:/switch/`.
Use the same 32-bit no-alias NSP,
Medium preset, renderer, clock and plugins as the supplied Kit12 test. Select
Debug launch, then Exhibition -> controller -> team selection -> kick-off.
Retain `fex-runtime.log` on success as well as failure. If a stall leaves HOME
responsive, allow about 15 seconds of diagnostics and close with HOME -> X.
The package includes Kit12 r2 NRO rollback. Normal launch stays quiet.
