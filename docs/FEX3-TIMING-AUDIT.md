# FEX3: separate throughput from the reported 2x motion

The Fast-vector device test restores the reported accelerated game motion and
has worse camera pacing than Fastest. Do not promote it as a speed fix. The
input is archived at `local/fex3/fast-vector-result/fex-runtime.log`, 111,241
bytes, SHA256 `915aedf3f349e20d5edde329a35a0998d0e726ab4e98ab48c9fac68d54288f11`.

The final six complete present windows average 32.622 native API presents/s,
but include transitions. Three intervals average about 30-31 presents/s.
These are not distinct displayed frames, simulation updates or a measured
30 FPS gameplay benchmark. Fast's earlier final six windows averaged 13.938
presents/s; the scenes and run lengths are not controlled, so this is not a
2.34x speedup claim. Lower throughput could mask an underlying speed issue.

At the last thread report, thread 172 uses 83.8% of a core, thread 4 uses
68.2%, and the total is 2.34 cores. Native present in the final window takes
about 0.63 ms/call; this does not measure GPU execution. The shared-clock
updater averages 1.038 ms, and main-thread requested 4 ms sleeps total about
1.202 s for 1.200 s requested. None of those host observations establishes
that the game's own time conversion, frame skipping or animation steps are
correct. There are no `[EXC]` or `[EXIT]` records in this input.

## This package

`dist/pes13-fex3-timing-audit/` is a five-file overlay, without a ZIP. It selects
the existing Fastest profile because the tester reports better camera motion
there. FEX's translator, x87 precision and profile implementation are unchanged
from the paired Fast-vector DLL. The only native source changes from that
build are `runtime.c` and the bounded diagnostic reader in `virtual.c`.

* Periodic diagnostic messages no longer call `fflush` for every `[FEX...]`
  line. A thread-local batch surrounds the log-flusher's reports. Its existing
  five-second flush commits the group. Faults/exits remain immediate, including
  faults from another thread while a batch is active. The duplicate BOOT flush
  is removed. This removes redundant SD I/O, not the underlying 3D calculation
  workload; its actual frame-time benefit has not been measured on hardware.
* An opt-in reader records the PES display/timing object, frame-skipping flags,
  frame-pacer state and guest-computed QPC-derived timestamps every five
  seconds. It never suspends a guest thread or runs inside present/delay/JIT
  hot paths. It neither scales time nor imposes a frame cap.

Fastest remains an experimental relaxed-memory-ordering profile. This package
does **not** claim the 2x issue or the CPU bottleneck is fixed, nor that gameplay
will sustain 30 FPS. It supplies the missing evidence needed to choose the
next correction without another blind preset change. The user has observed
the speed issue with automatic DXVK limiting enabled as well as disabled.

The existing synchronous self-suspend behavior and `fex_targeted_wake=0` are
preserved. DXVK, its configuration, game files, saves and `settings.dat` are
not modified by this overlay. No frame-skipping or game-code patch is applied.

## Reading the evidence

The probe recognizes three 16-byte code fingerprints from the locally
supported PES image. Unsupported or not-yet-mapped images are skipped. Guest
memory is copied through Wine's `virtual_uninterrupted_read_memory`, which
holds the VM mutex and checks read permission on each page. Short reads,
out-of-range pointers, a wrong vtable and a changed object pointer are rejected.
This prevents a diagnostic from blindly dereferencing a stale guest pointer.

* `[FEX3-GAME]` includes settings bits and raw `scale_bits` from the display /
  timing object: `3f800000` = 1.0, `3fc00000` = 1.5, `40000000` = 2.0. The
  executable contains a setter selecting these values. Its relevance to live
  simulation must be confirmed; this is not a direct scoreboard-speed reading.
* `[FEX3-GCLOCK]` compares physical elapsed time with timestamps produced by
  PES's own QPC-to-microseconds path. Those timestamps are updated at frame
  boundaries. A stopped/reset ring or a mode transition invalidates a simple
  clock-rate inference. Look for sustained behavior during continuous play.
* `[FEX3-PACER]` records the selected refresh/interval, fixed-rate bits and
  adaptive pacing state. The snapshot can straddle guest writes; it does not
  lock the game's own objects. Do not diagnose a race from one outlier.

The ring at `0x018ae4f8` is updated by the frame-end routine at `0x0113ee10`;
`0x01119a60` converts QPC/QPF to microseconds. The timing object is referenced
through `0x019bd154`, its scale is at offset `0x20`, and the settings flags are
at `0x019bc826`. These constants are diagnostic-only and fingerprint guarded.
The executable used for static analysis is SHA256
`95a62510d2878282d024c68f855f5eb051ff14d1d36614713d4ae151bd12d6ce`;
no game executable is distributed in the overlay.

## Device check

1. Close PES through HOME -> X. Copy `switch` from this package to the SD root
   and overwrite all five files. The forwarder still targets
   `switch/pes13-fex/pes13-fex.nro`.
2. Keep CPU/GPU/RAM clocks constant during this run. Use the same match length
   and match settings as before. Play through kick-off and an event/replay.
3. Preserve `switch/pes13-fex/fex-runtime.log` before launching again. If
   possible, note the scoreboard advance over 30 real seconds of continuous
   play, excluding stoppages, compared with normal-speed play at the same
   match length. PES's match clock is accelerated by design; its absolute
   numeric rate alone does not prove this bug.

Expected startup markers: `[BUILD] pes13-fex3-timing-audit`,
`[FEX3-PRESET] fastest ...`, `[FEX3-GAME] enabled=1`.

`fex_game_timing=0` disables only the reader after a restart; batching remains.
For a same-binary Fast comparison set `fex_fastest=0` and retain
`fex_fast=1, fex_relaxed_vectors=0`. No additional package is required.
Full binary rollback remains in `dist/pes13-fex3-fast-vector/` or
`dist/pes13-fex3-speed-fast/`; neither is changed by the packager.

## Local validation

The package includes hash-bound reports for the frame/pipeline/synchronization
observers, native ARM64 self-suspend and profile/heap checks, and the new
read-only probe/logger tests. The latter runs ASan/UBSan and tests inaccessible
memory, identity mismatches, object replacement, ring validation, synthetic
1x/2x timestamp histories, and cross-thread fault flushing during a 32-line
metrics batch. These tests do not execute a PES match or emulate the Switch GPU.

Build using `tools/build-fex-runtime.py --integration --native-only --jobs 4`,
archive the output under `local/fex3/timing-audit/runtime/`, run the reports
listed in `tools/package-fex3-timing-audit.py`, then run that packager.
`tools/analyze-fex-game-timing.py` decodes a subsequent device log; its output
preserves raw timing fields and their interpretation limits.
