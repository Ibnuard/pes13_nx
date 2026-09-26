# FEX3: Fast with optional vector ordering relaxation

## Device evidence, 26 September 2026

The tester reports normal game speed with Fast, but low gameplay FPS. CPU OC
was held constant throughout this run. The input is `fex-runtime-fast.log`,
130,348 bytes, SHA256
`7b9793cb70c2feedf9776aad193c2978d0b6192f81982b37c3c8a3f37eb21bcd`.
The archived input and reproducible analysis are in `local/fex3/fast-result/`.

The log identifies `pes13-fex3-sync-recovery`, Fast, x87 reduced precision,
and all three TSO options enabled. DXVK remains 3.1.1, with
`d3d9.maxFrameRate=-1` and `d3d9.maxFrameLatency=1`.

* The final six measurement windows contain 841 successful presents over
  60.337 seconds: **13.938 host presents/second**. These count API calls,
  not distinct displayed frames or simulation ticks.
* At approximately 236 seconds, guest thread 172 uses 82.7% of a core, the
  main guest thread 4 uses 52.7%, and thread 124 uses 33.9%. All 68 threads
  together use 2.17 cores; not every core is saturated.
* In the final window, the average gap entering present is 74.224 ms. Native
  present takes 0.232 ms, including a 0.223 ms driver call. Native acquire is
  0.085 ms, queue submit 0.135 ms, fence wait 0.036 ms, and semaphore wait
  3.023 ms per call. These CPU wall times do not measure GPU execution and
  must not simply be added across concurrent stages.
* The shared clock updates every 1.025 ms on average in that window. Thread
  4's 388 requested 4 ms sleeps total 1.552 s requested and 1.553669 s actual.
  Other threads accumulate scheduling/wait excess; that is not evidence of
  the guest clock running twice as fast.
* There are no `[EXC]` or `[EXIT]` lines, native heap failures, or section
  failures in this input. Self-suspend reports 21,343 returns from 21,343
  calls with nobody left parked at the final sample.

The evidence points toward work and synchronization before native submission.
It does not identify a specific expensive guest function or prove the GPU has
no remaining cost. Nor does the log identify the exact throw-in interval.

Fast's normal speed is the tester's observation. Lower throughput by itself
could hide an accelerated simulation, so preserve the same match settings and
compare the scoreboard over a fixed real-time interval as well as camera motion.
Earlier tests also showed accelerated motion while the automatic DXVK limiter
was enabled; this change does not attribute that symptom to the limiter.

## Controlled change

FEX is still pinned to `e2f973fe931e6dc2ce523795e51ca1ac3ca85816`.
In that source, `FEXCore/Source/Interface/Core/JIT/MemoryOps.cpp` emits
`DMB ISHLD` for ordered vector loads and `DMB ISH` for ordered vector stores.
`Context::UpdateAtomicTSOEmulationConfig()` treats scalar, vector, and
REP MOVS/STOS ordering separately. The upstream explanation of
[vector and memcpy TSO costs](https://fex-emu.com/FEX-2404/) supports testing
these independently. Its recommendation for newer LRCPC CPUs is not a Switch
Cortex-A57 recommendation or a promised speedup here.

The new profile changes **only vector TSO** relative to the tested Fast:

| Setting | Fast control | Fast-vector candidate | Fastest |
| --- | --- | --- | --- |
| Profile number | 1 | 3 | 2 |
| x87 reduced precision | 64-bit | 64-bit | 64-bit |
| Scalar TSO | on | on | off |
| Vector TSO | on | off | off |
| REP MOVS/STOS TSO | on | on | off |
| Half-barrier, multiblock, maxinst | 1 / 1 / 5000 | 1 / 1 / 5000 | 1 / 1 / 5000 |
| Self-modifying code tracking | MTRACK | MTRACK | MTRACK |

This removes ordering barriers around vector memory accesses, not their
arithmetic work. Scalar TSO, REP ordering and explicit atomic/LOCK operations
remain as in Fast. Guest threads sharing vector data can still depend on the
removed ordering: this is an experiment, not proof of x86 memory-model correctness.
It may reintroduce timing or compatibility problems and has no measured FPS
benefit until tested on Switch.

The host and FEX DLL are rebuilt together. Their 96-byte ABI layout stays at
version 3, with the added profile number. Old profile numbers and their option
values stay unchanged. Select the candidate at startup with:

```ini
run_guest_tests=0
fex_fast=1
fex_fastest=0
fex_relaxed_vectors=1
fex_targeted_wake=0
```

Missing `fex_relaxed_vectors` defaults to 0. Guest tests always select control.
Fastest retains its previous precedence if explicitly enabled. Vector relaxation
has no effect when Fast is disabled and Fastest is disabled. No live profile
switching is supported; restart the application after an edit.

## Install and compare

Copy the `switch` folder from `dist/pes13-fex3-fast-vector/` to the SD root,
overwriting all five supplied files, including the NRO, `libwow64fex.dll` and
`configuration.ini`. Use the existing `switch/pes13-fex/pes13-fex.nro` forwarder.
The package contains no game files, saves or replacement `settings.dat`, and
does not reset shader caches. It is a folder, with no ZIP.

Expected startup:

```text
[BUILD] pes13-fex3-fast-vector
[FEX3-PRESET] fast-vector x87=64 scalar_tso=1 vector_tso=0 memcpy_tso=1 ...
[FEX3-SYNC] startup targeted=0
```

Use the same CPU OC for the whole run, with the same teams, stadium, match
length and game-speed settings. Reach kick-off, play through several passes
and a replay/set piece, and observe both motion and the scoreboard. Save
`fex-runtime.log` before restarting. There is no need to change clocks mid-run.

For the exact Fast option control on the **same new binaries**, set only
`fex_relaxed_vectors=0` and restart. The preset line must change back to
`fast ... vector_tso=1`. If accelerated motion or a hang returns, this is also
the immediate rollback. The earlier `dist/pes13-fex3-speed-fast/` remains intact
for a full binary rollback.

QPC/TSC clocks, DXVK binaries/configuration, frame latency, scheduler, x87
precision and the synchronous self-suspend fix are unchanged. No GPU clock,
game executable, frame-skip setting or FPS cap is changed by this candidate.

## Local verification

The package manifest records both binary hashes and validation reports. The
native ARM64 selector is executed with all 16 startup flag combinations and
invalid profile numbers. The PE DLL's real FEX typed configuration getters
are executed for all four profiles, including restoring strict vector TSO
after the candidate. Linked heap/ABI tests and native self-suspend/pipeline
checks run against the delivered binaries; observer source tests use ASan/UBSan.

These checks verify selection, configuration and integration, not real hardware
memory ordering, PES compatibility, or FPS. The next device run is still required.
