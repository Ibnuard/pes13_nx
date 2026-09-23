# PERF17B — bind the hotspot experiment to the original file header

This fixes the activation failure in the [PERF17 hardware log](PERF17-RESULT.md).
It retains the same scoped BIGBLOCK=1 experiment and bounded code capture.
The stable PERF15 mapping/exception fixes, ABI4, DXVK 3.1.1, global
Compatible profile, game, saves, settings and controllers remain.

The original PERF17 build's `identity=-1 selected=0 completed=0` means no
experimental blocks ran. It did not measure the proposed optimization.
The exact cause of the header check failure was not recorded.

## Fix

Immediately after the loader maps and describes its main target, the
runtime reads 512 bytes from that same target file. It checks the original
header fingerprint (FNV-1a `0x4e46d440`) and the loader's actual image base
`0x400000` and size `0x189a000`, then publishes the result before starting
guest code. The translator reads this result instead of inspecting live
headers. Later header changes cannot invalidate a successful file check.
An early unbound state remains a temporary baseline fallback.

The check still rejects a different file header, a wrong base/size, a
missing file, or a short read. A single startup line records disk and
initial loaded header hashes, byte count, base, size, and identity:

- `identity=1`: the supported file header and mapped image match.
- `identity=-1`: file-header mismatch.
- `identity=-2`: unexpected mapped base or size.
- `identity=-3`: missing/short header read.
- `identity=0`: the main image has not been bound yet.

This is a version check, not cryptographic authentication. No game file is
modified, and the snapshot format and `tools/decode-perf17.py` are unchanged.
Four selected address ranges, activation after the first successful Vulkan
present, and preservation of all global Compatible options follow PERF17.
Old compiled blocks are still not forcibly invalidated. Capture remains
at most eight blocks / 128 KiB raw code, approximately 400 KiB formatted
log, with no continuous sampler or per-frame hook.

## Install and verify

1. Close with HOME → X → Close. Extract `pes13-perf17b-hotblocks.zip` at
   the SD root and overwrite. Use the same forwarder and single
   `switch/pes13-nx/pes13-nx.nro`.
2. Keep the same clocks and settings. Stay on the 3D team/player screen
   for 30 real seconds, then in a match for 60 real seconds.
3. Preserve `switch/pes13-nx/pes13-nx.log`. Expected build marker:
   `pes13-nx-0.2.0-perf17b-image-identity`. Check `[PERF17-IMAGE] source=file
   ... identity=1`, then nonzero `selected`/`completed` and block snapshots.
   If those remain zero, report the log without changing Box64 flags or EXE.

`pes13-perf17b-control.zip` disables hotblocks on the same new NRO while
retaining bounded capture. `pes13-perf17b-rollback.zip` restores the exact
stable PERF15 NRO/ABI4 pair and DXVK, with both experiment flags off.

## Validation and limits

ASan/UBSan host tests exercise valid binding, unbound fallback, short reads,
wrong mapped base/size, altered file headers, successful binding followed
by in-memory header changes, and the existing range/preset/capture tests.
The loader hook is checked to occur before guest initialization. Build and
package checks cover the NRO metadata/icon, ABI4 and DXVK hashes, archive
contents, and restoration of baseline source. These tests do not execute
the game on Switch. Activation and any FPS effect remain hardware-unverified.
