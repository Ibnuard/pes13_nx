# Fextendo: periodic CPU burst trial

This is one combined update for `pes13-fextendo-launcher.zip`. It disables
DXVK memory defragmentation and adds bounded native memory-query timing. It is
a test candidate, not a claim that Switch stutter or first kickoff is fixed.

## Install and compare

1. Close PES completely with HOME → X.
2. Copy this ZIP's `switch/` folder to the SD root, replacing its **three files**:
   `pes13-fex.nro`, `drive_c/PES13/dxvk.conf`, and
   `launcher/presets/dxvk.conf` under `switch/pes13-fex/`.
3. Launch the existing Fextendo launcher and play with the same preset and
   clocks as the previous run. Start with the reported CPU boost 1728 profile
   to make the comparison useful; then try stock clocks separately.
4. Compare first kickoff, airborne/fast balls, fast camera movement, and a
   second match. Copy `fex-runtime.log` after closing. Keep existing caches for
   this comparison; deleting them would add another variable.

The launcher template is included because selecting any preset writes the
active DXVK configuration again. This update leaves all settings.dat files,
controller bindings, selected preset, assets, and DLLs in place. VSync remains
ON with the previous two-frame queue. Canonical PES settings remain
`C:\KONAMI\Pro Evolution Soccer 2013\settings.dat`.

To return to the exact delivered launcher baseline, close PES and copy
`rollback/switch/` to the SD root. These three rollback files are byte-identical
to the verified previous ZIP. This update requires that previous launcher
installation; it is not a standalone game distribution.

## What the latest log shows

Input: 290,532 bytes, SHA-256
`d4bd5f2de54efd400d6b84036059ef9d620a4bcc7ac0268d49101047ec3f370d`.
Build marker: `pes13-fextendo-v1`; DXVK reports v3.1.1, three guest processors,
one compiler thread, VSync ON, and a loaded shader cache.

There are 389 bounded gap records over 50 ms; 143 have valid presenting-thread
CPU time of at least 25 ms. In the last 20 such records, CPU time is
28.588–31.129 ms (median 29.334 ms). Of their 19 intervals, 18 are within
450–550 ms, with one 967.911 ms interval. All 20 use native handle 2326984.
The analyzer saves the exact selected rows rather than treating this tail as
the entire run. Missing records and the 50 ms threshold can hide other gaps.

Upstream [DXVK 3.1.1 memory allocator](https://github.com/doitsujin/dxvk/blob/v3.1.1/src/dxvk/dxvk_memory.cpp)
runs maintenance every 500 ms: refresh budgets, free unused chunks, clean
allocation caches, and optionally defragment/evict resources. The
[submission queue](https://github.com/doitsujin/dxvk/blob/v3.1.1/src/dxvk/dxvk_queue.cpp)
invokes this on the thread which also submits/presents. The
[documented debug option](https://github.com/doitsujin/dxvk/blob/v3.1.1/dxvk.conf)
`dxvk.enableMemoryDefrag = False` disables that relocation/eviction branch.
Other maintenance remains active. It may retain more fragmented memory, so
longer sessions and memory-pressure behavior still need hardware testing.

This matching cadence is a concrete hypothesis, not proof of which operation
costs 29 ms. The locally linked Switch Mesa implementation queries free heap
space using `mallinfo()` for Vulkan memory budgets. Its actual cost is not yet
measured. The new observer distinguishes native query time from the rest of
DXVK maintenance; it does not cache, suppress, or change budget results.

Registered threads briefly account for about 2.4 CPU cores in gameplay.
Restricting execution to two physical cores can therefore increase contention.
The third displayed core likely corresponds to index 2, but the log does not
map handle 2326984 to that physical core or to a Wine thread ID. Monitor 99%
is useful correlation, not proof that disabling that core will fix pacing.
The fourth core's shared status does not explain this record by itself.

Compilation also continues in this run. This trial does not establish that
all early-game stutter, first kickoff, or event slow motion share one cause.

## Implementation and verification

Runtime marker: `pes13-fextendo-mem-audit`. `[FEX3-MEMQUERY]` records contain
begin/end system ticks, native handle, wall time and valid thread CPU time.
Only calls >=1 ms get individual records, bounded to 32 per report. A summary
also counts faster queries. Producers allocate nothing, write no log files,
and use a try-lock; the existing logger drains every approximately 10 seconds.
The observer makes two CPU-counter syscalls per memory-properties query,
not per frame. Existing `fex_gap_probe=0` disables both timing observers.

Four Wine Vulkan wrappers cover the 32/64-bit core/KHR memory-properties2
entry points. Inputs, output conversion, driver calls and return values are
preserved. Native changes are confined to `runtime.c` and `vulkan_thunks.c`;
the FEX DLL, PE DLLs, Mesa, libnx, affinities and yield policy match baseline.

The package binds ten passing check reports to one ELF: memory observer,
launcher, gap timing, stable balance, bounded yield, worker cores, resume,
pipeline, JIT logger and unwind. Observer checks include ASan/UBSan, overflow,
contention, concurrent calls, failed CPU counters, disable behavior, and
execution of the linked ARM64 timing functions. Stripping only the four
wrappers reproduces the baseline Vulkan thunk source hash exactly.
These checks establish code behavior and packaging integrity, not game FPS.

`tools/analyze-fex-memory-gaps.py` accepts old or new logs. For new logs it
also matches slow queries contained in a gap on the same native handle.
All conclusions still require the next Switch run.
