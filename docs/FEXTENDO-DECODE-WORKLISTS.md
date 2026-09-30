# FEXTendo: lower-cost FEX decoder worklists

This candidate reduces CPU work during first-use translation, including launches
with **FEX disk cache OFF**. It does not require a previous match, a particular
team, or a populated cache. It is an optimization candidate, not a confirmed
fix for the first-kickoff freeze.

## Install on an existing v3.6 installation

Close FEXTendo completely. Copy the package's top-level `switch/` directory to
the SD-card root, replacing only:

```text
switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll
```

The launcher NRO and forwarder do not need updating. Keep the existing renderer,
clock, resolution, teams/camera preferences and game files. This package contains
no game content and does not replace configuration or saves.

For the performance comparison, retain these values in the existing INI (edit
existing keys rather than adding duplicates):

```ini
fex_short_trace_off=1
fex_hot_profile=0
fex_fast_api=1
fex_diskcache=0
```

The startup log must include:

```text
[FEX3-DECODE] v1 inline worklists=64; ordered-tree overflow; no persistent cache required
```

The app version remains v3.6/0.3.7 because this update replaces the FEX DLL only.
Use the marker and package manifest to distinguish this candidate. If it
regresses, close the app and copy `rollback/switch/` to the SD root to restore
the exact previous v3.6 DLL.

## What changed and why

The latest quiet capture still records 6,900 CompileCode calls and 7.863 seconds
of completed-call wall time in an early 50-second compiler-uptime interval.
Native heap counters already reach 3,749,009 allocations at compiler uptime
130.202 s. These are all FEX-private allocations, **not an allocation profile
attributing every call to the decoder**.

Inspection found a concrete source of avoidable work: the decoder stores
current branch targets, pending blocks and visited blocks in `std::set` trees.
Inserting new addresses allocates nodes; clearing/consuming them frees nodes.
The port's allocator routes these operations through the PE/native bridge.

The three decoder-private collections now hold up to 64 sorted unique addresses
inside the decoder. Small compilations need no node allocation for these
collections, even on the very first compilation. Larger collections spill to
the original FEX-allocated ordered tree with no target limit or truncation.
Clear returns the collection to its inline mode. Persistent compiler caches
and general-purpose heap allocation are unchanged.

The replacement preserves lowest-address-first decoding, deduplication and the
decoder's merge-then-clear result. It does not change which x86 instructions
are decoded, JIT128, instruction lowering, optimization passes, executable-code
invalidation, TSO, Wine waits, clocks or thread affinity. Inline storage adds
roughly 1.6 KiB per decoder, with no shared lock or global allocation pool.

## Validation and limits

- 200,000 randomized operations compared against ordered-tree behavior.
- Inline/overflow merges, duplicates, unsigned address extrema, 63/64/65-entry
  boundaries, 5,000 entries and reset behavior.
- Failed spill allocation preserves all existing addresses.
- ASan/UBSan and optimized host runs; allocation/free balance checked.
- Generated decoder sources checked against the pinned upstream source with
  only the declared worklist substitutions allowed.
- Linked ARM64 checks for heap/profile contracts, dispatcher/cache behavior,
  lookup hashing, executable-code guards and JIT metric/report behavior.

Synthetic worklist results (each run starts with empty collections):

| Blocks per run | Runs | Previous node allocations | Candidate node allocations |
| ---: | ---: | ---: | ---: |
| 8 | 10,000 | 220,000 | 0 |
| 32 | 10,000 | 940,000 | 0 |
| 64 | 10,000 | 1,900,000 | 0 |
| 128 | 1,000 | 382,000 | 128,000 |
| 512 | 1,000 | 1,534,000 | 512,000 |

These counts demonstrate removal of work in the targeted data structures. They
do not measure the full compiler, real PES13 allocation distribution, Switch
FPS, or kickoff freeze duration. The ARM64 tests model platform boundaries;
full game compatibility still requires the Switch test.

## Device check

Start with a fully closed app and play through the first kickoff, first shot
and lofted pass. Save the log before opening the app again. Compare the symptom
with the current quiet v3.6 setup; note approximate time since Play for a stall.
Keep existing caches rather than deleting them, while leaving the FEX disk-cache
flag OFF for this comparison. A later fresh launch with different teams or a
different stadium tests broader behavior; success in a repeated match alone
does not establish the goal.

The next decision should use first-use compiler work and frame pacing, with
camera smoothness preserved. Cache persistence is a separate complementary
effort. If the measured compile reduction does not explain the remaining stall,
the next target is the game-thread/API/wait path, not another unsupported claim
that caching or core redistribution must fix everything.

FEX remains the upstream FEX-Emu project. This decoder-storage adaptation is a
local Horizon-port change built against the pinned upstream revision; see
[the provenance statement](FEX-PORT-PROVENANCE.md).
