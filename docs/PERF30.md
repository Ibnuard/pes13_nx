# PERF30: native submit and audio diagnosis

PERF30 measures where the runtime spends time when goal/foul/replay transitions
leave gameplay permanently slower. It is a diagnostic build, not a confirmed
performance fix. Match 30/60 FPS and the intermittent startup fault remain
unresolved. The last measured PERF29 control segment fell from 16.58 to 3.00
successful presents/s; mean host submit time rose from 1.139 to 55.642 ms.
This is host wall time, not a measurement of GPU execution.

## Evidence available for this continuation

The user identifies their latest test as **PERF29 control-sampling** and reports
the slowdown persisting until exit. However, the four supplied `previous-*`
files are byte-identical to already archived runs. The current `pes13-nx.log`
is absent from the supplied folder. We cannot attribute those old measurements
to the latest sampling test or infer its sampled stacks.

| Supplied file | Same archived run | SHA-256 prefix |
| --- | --- | --- |
| previous-1 | PERF29 control, CPU sampling off, 180 s | 3e0ca96ffae6bb64 |
| previous-2 | PERF29 control startup fault | 2a318d696f8fb750 |
| previous-3 | PERF29 block-growth experiment, 120 s | 08265f028614ea2b |
| previous-4 | Historical PERF28 sampled run, 370 s | 3f299c868e775b9f |

Full hashes and unmodified private copies are in
`local/perf30/user-input/input-manifest.json` and `results/`.
[The control report](PERF29-CONTROL-RESULT.md) contains the detailed evidence:
the stall reproduces with block growth disabled, while total reported thread
occupancy falls from 2.92 to 1.95 cores. Thus the transition is not explained
simply by all CPU cores reaching capacity. Ordinary match throughput and the
persistent event-associated stall may have different causes.

## What changed

The NRO links a private, instrumented copy of the existing Mesa library.
Four source files gain timing around queue locks, driver submission, state
updates, upload flush/wait, command processing, signaling, host sync waits,
Horizon channel locks, submit ordering, entry reservation, in-flight throttling,
and native kickoff. Audio measurements cover producer release, audio mutex
waits and pumping. Gauges capture shader local-memory allocation, descriptor
pool sizes and audio held/submitted/played frame counts.

No queue, fence, buffer-size or rendering decision is deliberately changed.
The existing math/copy translations and compatibility policy remain: global
SAFEFLAGS=2, STRONGMEM=1, FASTNAN=0, X87DOUBLE=1, BIGBLOCK=0 and CALLRET=0,
with the existing scoped game FASTROUND=1/CALLRET=2 policy. Experimental
PERF29 worker block growth is disabled. CPU stack sampling is disabled in both
configuration layers to avoid combining two diagnostic costs.

Hot paths only record timestamps and bounded in-memory data. The existing
roughly 10-second reporter writes summaries; no new per-submit SD-card write
or thread suspension is introduced. Instrumentation still costs CPU time,
so use the quiet overlay to check whether it affects symptoms.

## Install and test

1. Close the application fully with HOME → X → Close.
2. Extract **`pes13-perf30-submit-diagnostics.zip`** to the SD root, overwriting
   included files. It upgrades the existing installation and includes exactly
   one NRO: `switch/pes13-nx/pes13-nx.nro`. Keep the existing forwarder.
3. Keep clocks, teams, stadium, graphics and caches unchanged. The previous
   comparison used CPU 1728 / GPU 768 / RAM 1600 MHz; this is a comparison
   condition, not a new overclock recommendation.
4. Play until a goal/foul/replay reproduces the persistent slowdown. Record
   rough elapsed real time and whether normal speed returns after replay.
   If possible, leave it running another 30–60 seconds to capture the state.
5. Copy **`switch/pes13-nx/pes13-nx.log`**, plus its previous-1 through previous-4
   logs, before further launches rotate the files.

Expected build marker: `pes13-nx-0.2.0-perf30-submit-stages`.
Expected enabled marker: `[PERF30] submit_diagnostics=1`; worker growth is 0
and CPU sampler is off. Packaging preserves the icon and single-NRO layout.
Game executables, saves, registry/installation metadata and `settings.dat`
are not included or replaced by these upgrade packages.

After testing, **`pes13-perf30-quiet.zip`** disables the new diagnostics and
keeps CPU sampling and worker growth off. It contains configuration only and
requires the PERF30 NRO. Disabled measurement wrappers still have a small
call/check cost; this is not byte-identical to the old runtime. To restore
the previous runtime as well, install
**`pes13-perf30-rollback-perf29.zip`**, which includes the exact prior PERF29
NRO and its quiet control configuration. Reinstall the main PERF30 package
to enable diagnosis again.

## Reading measurements

- `STAGE30`: interval completed-call count, total host microseconds,
  count at least 100 ms, and **launch-wide** maximum. Stage times nest and can
  overlap across threads; do not sum them as frame time or GPU utilization.
- `ACTIVE30`: a coherent single-attempt observation of an active stage at least
  100 ms old. Reports native thread handle, opaque object address and owner
  slot. These are not Wine thread IDs. No object memory is dereferenced.
- `SLOW30`: up to 16 completed slow spans per reporting interval, with absolute
  system tick at entry. Nested spans may describe the same delay. Overflow is
  counted; this is not a complete event trace.
- `VALUE30`: last observed and launch-wide peak values. SLM values are allocated
  bytes per warp/TPC, descriptor pools are allocation counts; neither is GPU
  utilization. Audio gauges are frames, not audio content or unique glitches.

Owner slots are fixed at 64 and retained for the process lifetime. Once they
are exhausted, aggregate timing still works but active-stage observations of
new owners stop; `owner_overflow` makes that visible. Native handles can be
reused. Counter fields are read independently, so interval averages are
approximate at report boundaries. A long stage includes scheduling/wait time
and does not prove that stage's code consumed the CPU throughout.

## Build and verification

WSL, without Docker:

```sh
python3 tests/perf30_archive.py
python3 tests/perf30_analysis.py
python3 tools/run-perf30-build.py
python3 tools/package-perf30.py
```

Extract measurements with `python3 tools/analyze-perf30.py path/to/pes13-nx.log
--output local/perf30/test-analysis.json`. This keeps interval counters and
launch-wide maxima separate and labels logs without PERF30 reports.

This incremental build requires the pinned PERF29 build workspace, its test
reports and previous release archives. It is not a clean-machine bootstrap.
The Mesa source pin is `b297e230ef88c6c88df2561becf864f979f494a6`; Box64 remains
`2f130fab1d6e1a4ee8a71dc60cfdfcc839ad192a` with ABI 4. Mesa copies use their
existing exact cross-compiler commands. The original Mesa source/SDK remain
unchanged; modified Wine build inputs are restored and hash-checked.

Verification checks linked native/audio measurement calls, unchanged unrelated
Mesa archive members (including duplicate object names), retained CPU emitters,
build identity, NRO metadata, package hashes and source restoration. Native
host tests exercise nested timing, disabled mode, concurrent publication,
bounded overflow and gauges with address/undefined-behavior sanitizers.
These checks do not run PES on Switch or establish performance improvement.
