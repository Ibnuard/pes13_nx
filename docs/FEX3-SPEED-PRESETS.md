# FEX3: separate simulation speed from rendering throughput

The sync-recovery run reaches gameplay again. The tester now explicitly
corrects the earlier report: **the scoreboard clock as well as the players
speeds up after CPU OC**. Stock clocks are too choppy to judge whether the
same speed error already exists. Do not retain the previous assumption that
only animation jumps while the match clock remains correct.

The tester also reports this symptom with DXVK's automatic limiter enabled,
before this project disabled it. That makes limiter removal an insufficient
explanation. The next comparison leaves the limiter unchanged.

## Evidence

Input: `local/fex3/sync-recovery-result/fex-runtime.log`, 148,671 bytes,
SHA-256 `eba8345652143aa0e91c26e47f7c7459e4dd1d798b74e84bbc1e5f484d5f5eea`.
Use `tools/analyze-fex-speed.py` to reproduce `analysis.json` beside that log.

- Build `pes13-fex3-sync-recovery`, targeted wakeups disabled, FEX Fastest.
- DXVK 3.1.1, FIFO, `maxFrameRate=-1`, `maxFrameLatency=1`.
- Several late windows approach 60 native presents/s. These are not proof
  of 60 unique rendered frames or correctly paced simulation.
- The log has no scoreboard-time or CPU-clock-change samples, so it cannot
  identify an exact speed multiplier or conclusively attribute it to FEX.

The native QPC path reports 10 MHz and converts Horizon system ticks into
100 ns units. FEX's host and emitted cycle-counter paths use CNTPCT_EL0;
the startup preflight reports 19.2 MHz. No inspected preset scales either
clock. This is a source audit, not an on-device verification of every guest
timing calculation through JIT, x87, and game synchronization.

## Controlled preset comparison

These are this project's presets, defined in `src/fex/module_profile.cpp`,
not official upstream preset names.

| Variant | INI fast / fastest | x87 internal precision | Scalar / vector / memcpy TSO |
| --- | --- | --- | --- |
| Last tested Fastest | 1 / 1 | 64 bit | off / off / off |
| A: Fast | 1 / 0 | 64 bit | on / on / on |
| B: Control | 0 / 0 | 80 bit | on / on / on |

A restores x86 memory ordering around translated worker communication.
Relative to A, B changes only x87 reduced precision. Both retain multiblock,
maxinst=5000, MTRACK invalidation, native heap, synchronous self-suspend,
shared wakeups, the existing renderer, and the same timing policies.

There is no intentional 2x multiplier in Fastest. Relaxed ordering and
reduced precision can affect correctness; neither is established as the
cause here. Fast is the first candidate because it retains reduced x87
cost while removing the more aggressive ordering relaxation. Control is
an accuracy comparison and can be slower. Slower output is not itself a fix.

## Deliverables and test

- `dist/pes13-fex3-speed-fast/switch`: A, test first.
- `dist/pes13-fex3-speed-control/switch`: B, if A still runs too fast.

Each is a complete five-file update to the existing FEX installation, with
one NRO and no ZIP. This is a **configuration experiment, not a newly
compiled runtime**. The NRO, FEX DLL, ntdll DLL and dxvk.conf are byte-for-byte
identical to sync-recovery. Only `configuration.ini` changes. Consequently,
the build marker remains `pes13-fex3-sync-recovery`; distinguish the tests
using `[FEX3-PRESET] fast ...` or `[FEX3-PRESET] control ...` in the log.
Explicit INI values override residual legacy boolean files.

Close with HOME -> X, copy one package's `switch` folder to the SD root,
and overwrite all five files including the INI. Keep the existing forwarder
`switch/pes13-fex/pes13-fex.nro`. Restart between variants: presets are applied
before the FEX context is created and cannot be changed live.

For the first comparison, keep the **same CPU-only OC from launch** for both
variants. Keep match duration, game speed, teams, stadium and graphics the
same. During uninterrupted open play, record how much the scoreboard clock
advances over 30 real seconds, along with the visible movement. Exclude
pauses, replays and set pieces from that interval. PES's accelerated match
clock should not be compared to real seconds at a 1:1 rate; compare the
same match settings across runs. Preserve the log before restarting.

If A normalizes motion at comparable throughput, ordering is implicated.
If only B does so, reduced x87 precision is implicated. Neither outcome is
conclusive if correctness appears to improve merely because frame throughput
halves. If both remain fast, investigate guest timing/frame skipping and
suspend/resume ordering rather than progressively reducing the FPS cap.
Compare stock-clock performance separately after simulation speed is correct.

To restore the last tested Fastest configuration, use the preserved
`dist/pes13-fex3-sync-recovery/switch/pes13-fex/configuration.ini`, or restore
`fex_fast=1` and `fex_fastest=1` in the installed INI, then restart.

## Additional static finding

Read-only inspection of the user's original Settings.exe maps control 1104
to Vsync (flag 0x1) and control 1105 to Frame Skipping (flag 0x2).
Getters at 0x41bdd0/0x41bde0 and setters at 0x41be00/0x41be20 access the
settings word. The supplied production template's flags 0x028b enable both.
The inspected game copies the frame-skipping flag into a timing object's
offset 0x14 at 0x1118220. This offers a further path to investigate if the
preset comparison fails; it does **not** establish the Switch's current
settings.dat contents or prove a frame-skipping defect. No game executable
or settings/save file is changed or distributed by this experiment.

## Verification

The packager verifies the base manifest, exact NRO/DLL/config hashes, existing
seven validation reports and their linked ELF identity. Those existing tests
include actual ARM64 FEX typed configuration getters for Control, Fast,
Fastest and a return to Fast. Packaging checks ensure the only payload delta
is the intended INI values, reject duplicate keys and unexpected files, and
preserve the earlier checkpoint. They do not prove Switch gameplay speed,
compatibility or performance. No hardware success or FPS gain is claimed.
