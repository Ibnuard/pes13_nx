# FEXTendo v3.6 — shorter native API paths and block profiling

App **0.3.7**, build `pes13-fextendo-fast-api-v1`. This is a device-test
candidate. The native NRO and FEX DLL both changed; a Switch test is still
needed to measure frame-time improvement and check gameplay compatibility.

## Install and first test

1. Fully close FEXTendo. Copy **only the outer `switch/` directory** from
   the ZIP to the SD root, overwriting the matching files in a working v3.5
   installation. This replaces both `pes13-fex.nro` and
   `drive_c/windows/system32/libwow64fex.dll`. Keep both from this package.
2. A forwarder opening `switch/pes13-fex/pes13-fex.nro` can keep that path.
   A forwarder embedding an NRO needs its binary updated.
3. An existing `configuration.ini` takes priority over standalone flags.
   If these keys already exist, use the values below; do not replace the
   entire INI. Otherwise the included flag files select them.

   ```ini
   fex_polling=1
   fex_fast_api=1
   fex_hot_profile=0
   fex_short_trace_off=0
   fex_dxvk_balance=1
   fex_auto_core3=0
   fex_jit_small=1
   fex_jit_large=0
   ```

   Keep `no_balance=0` if present. Do not change renderer, resolution, clock
   settings or caches while comparing this candidate with the previous one.
   The package preserves the selected renderer and other launcher preferences.

Use DXVK **3.1.1**, Debug timestamp ON, and the same
teams, stadium, camera, preset and clock settings as the previous test.
Start from a fully closed app, then play two matches without closing between
them. Note timestamps since Play for first kickoff, long passes, shots, and
any freeze. Save the log before opening the app again.

Expected markers:

```text
pes13-fextendo-fast-api-v1
[FEX3-FASTAPI] v1 enabled=1 ...
[FEX3-FASTAPI] qpc=... delay=... cumulative registered-slot calls
[FEX3-HOT] enabled=0 ...
[FEX3-JIT-CONFIG] maxinst=128
[FEX3-COMPILE] ...
[FEX3-BLOCK] rip=... total_us=... decode_us=... passes_us=... frontend_us=... backend_us=...
```

The fast-call counters count registered thread slots, not elapsed CPU time.
Compiler rows require short tracing ON and completed compiles in the window.
Absence of a row is not evidence that no work occurred.

## Implemented reductions

**Native QPC and non-alertable delay gateways.** The dispatcher checks the
exact service number, current service-table limit and handler pointer, and
verbose mode before selecting a smaller two-argument call frame. It avoids
the generic argument shuffle and the return-path TEB lookup. The original
Wine handlers still implement QPC and delay. Alertable requests, mismatched
handlers and other syscalls retain the generic path. Original arguments,
NTSTATUS, QPC frequency and timeout values are preserved.

A test executing the final linked ARM64 gateway, with clock/TLS boundaries
modeled, counted **161 instructions OFF versus 89 ON** for warmed QPC.
This is a gateway instruction count, **not a 45% game/FPS improvement**.
The x86-to-WOW64 transition and FEX context management still run. This
candidate does not implement a full direct guest-to-native QPC thunk.

**FEX scratch realloc.** Reallocations of the same size or a modest shrink
keep the existing block and skip native allocation, copy and free. Retained
capacity is at most 1.5 times the requested size; larger shrinks release it
through the existing allocator. Growth, allocation failure, zero-size free
and alignment behavior remain covered. This is capacity reuse, not a new
shared allocation pool. Its frequency and saved time on PES13 are not yet
measured.

## Locate the remaining expensive work

The previous capture showed 7,738 completed compiles / 8.445 seconds of
summed wall time in fully contained T+100–150 second windows, versus 382 /
0.516 seconds at T+350–400. Scheduling can overlap these measurements; they
are not CPU utilization or freeze duration. The log did not contain the
entry addresses needed to identify the most expensive individual blocks.
See `source/docs/FEXTENDO-V3.5-DEVICE-REVIEW.md` for the audit and limits.

The new compiler trace records guest entry address, calls, peak/total wall
time, decode, IR passes, complete frontend and backend durations, code size,
and generated/raced/empty outcomes. It uses 2,048 fixed slots, at most 16
probes, a producer try-lock and drop counters. Every existing five-second
report emits the aggregate and the 12 most expensive **retained** entries.
Output goes through the bounded native queue; compile callbacks do not
write to SD. Frontend contains decode/passes, so those times must not be
added together. The ranking is not exhaustive, and in-flight compiles are
not yet represented. Capacity drops remain in aggregate totals; producer
lock-contention drops do not.

For an additional **diagnostic run**, copy `diagnostic/switch/` to the SD
root, or set `fex_hot_profile=1` in the INI if that key exists. This enables
FEX-aware samples of the two previously busiest threads every 50 ms. It
uses FEX x28/frame/block metadata instead of Box64 register mappings.
`[PROF]` records identify guest modules/entries, native offsets and SVC
residency. `[FEX3-HOT]` reports cumulative pause overhead and resume failures.
A block label is a compilation-unit entry, not an exact guest instruction.
Samples include blocked/waiting residency and are not pure on-CPU profiles.

Sampling requires the process's pause/context SVC permissions. If unavailable,
`[PROF] sampler not started` states the reason. Sampling can affect timing:
restore `fex_hot_profile=0` (or copy `sampling-off/switch/`) before performance
comparisons. If resume failures occur, stop using sampling and report the log.
Every successfully paused target receives an immediate resume attempt,
including failed context reads, with one retry on resume failure.

Analyze a captured log locally:

```sh
python3 tools/analyze-fextendo-hotspots.py device.log --range 100 150 --output hotspots.json
```

The tool keeps compile cost separate from sampled residency, ranks only
observed entries, preserves line references and rejects inconsistent Play
clocks. It does not infer missing block addresses from older logs. Native
sample offsets need the matching `local/fex3/fast-api-v1/runtime/reference/pes13-fex.elf`
for symbolization. Preserve this ELF with the build receipt.

## Controls and rollback

**Control correction after device review:** in the shipped v3.6 runtime,
a standalone `fex_fast_api` file containing `0` falls back to its default `1`.
To disable this API gateway, explicitly set **`fex_fast_api=0` inside
`configuration.ini`**. Replace an existing key instead of appending a duplicate;
the parser takes the first occurrence. The old ZIP's `control-fast-api/switch/`
file alone is therefore not a valid OFF comparison. This does not affect
`fex_short_trace_off=1`, whose default is `0`, or the normal fast-API-ON run.

| Directory copied to SD root | Result after restarting the app |
| --- | --- |
| Outer `switch/` | Fast native gateway ON, sampling OFF, short trace ON. |
| INI `fex_fast_api=0`, `fex_hot_profile=0` | Same new binaries; gateway OFF and sampling OFF. The legacy OFF file alone is ineffective. |
| `diagnostic/switch/` | Sampling ON and short trace ON; diagnostic run only. |
| `sampling-off/switch/` | Sampling OFF again. |
| `rollback/switch/` | Exact previous v3.5 NRO and FEX DLL plus compatible flags. |

Install the outer candidate first, then a control if needed. INI keys have
priority over these files. The same-binary control keeps the realloc change
and compiler telemetry; full rollback compares the whole release. To check
trace overhead separately, set `fex_short_trace_off=1` and leave sampling OFF.
Do not delete caches or change renderer during that comparison.

## Validation and attribution

All **22 groups** in `evidence/checks/` bind to the delivered binary or its
compiled source hashes. Gateway ARM64 execution tests cover argument/return
contracts, saved registers, x18 clobber, live-table guards, fallback, optional
QPC frequency and the same invalid-pointer fault location. Full asynchronous
exception delivery and real Switch scheduling still require device testing.

Allocator tests execute the linked DLL, including forced allocation failure
on retained shrinks and the capacity boundary. Sanitizer tests cover compiler
phase nesting, bounded collisions/contention, concurrent producer accounting,
output bounds, FEX metadata validation and exact sampler pause/resume paths.
Existing display, launch, Vulkan, deadline, balancing, lookup, memory and unwind
regression checks were rerun. Analyzer fixture checks also pass.

Renderer binaries, Mesa and guest Wine dependencies are unchanged. Graphics
already reach native ARM64 Vulkan; this release does not claim a newly enabled
universal FEX thunk. No game data is included. This remains a wrapper; supply your own PES13 v1.0.

FEX remains **FEX-Emu**. Switch port/integration and the changes described here
are **AndroSwitch Project / Ibnuard** work on the credited upstream projects.
The optional sampler adapts Wine-NX's existing profiler and retains its LGPL
notice. Corresponding modified sources, build recipes, baseline provenance
and `THIRD_PARTY.md` are included.
