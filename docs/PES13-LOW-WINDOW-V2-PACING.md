# PES13 Low Window v2: explicit frame-skipping policy

Copy-ready update, version **0.3.9-lw2**. This corrects a real settings migration
bug and adds Debug-only measurements for the reported jumping/2x movement.
It has not yet been tested on Switch; it does not claim that the speed symptom,
1–2 second pauses or prematch loading duration are solved.

## Install

1. Close PES with HOME → X. Copy this package's `switch/` folder to the SD root,
   overwriting **only** `/switch/pes13-fex/pes13-low-window.nro`.
2. Use the existing **PES13 Low Window** HOME tile and the already tested
   **FEXTendo Memory v1 TEST** boot entry. No new NSP, kernel or loader is
   included. If still in that boot entry, no reboot is needed for this update.
3. Keep the same renderer, preset and clocks as the successful LW1 match. For
   the first test use **Debug launch**. The startup banner must say `0.3.9-lw2`.
4. Play through prematch, kickoff, and a few fast passes. Save `fex-runtime.log`
   after closing. Note approximately when kickoff and the jumps happen.
5. To roll back the binary, copy `rollback/switch/` to the SD root. It contains
   the exact tested LW1 NRO. VSync on / frame skipping off remains the intended
   game settings policy; the rollback does not deliberately turn skipping on.

The ordinary `pes13-fex.nro`, game files, saves, Kitserver configuration,
configuration.ini, FEX Kit16 and DXVK Kit17 DLLs are not overwritten. No ZIP.

## Functional correction

The previous launcher copied a valid canonical `settings.dat`, enabled VSync
and XInput, then changed resolution/aspect/quality. It preserved every other
flag, including bit `0x0002` (Frame Skipping). Thus a valid older profile could
silently retain frame skipping even though the supplied templates disabled it.

LW2 explicitly clears that bit while enabling VSync and XInput. All unrelated
flags and controller mappings remain intact. It recalculates the CRC for all
three existing settings paths and reads them back before committing the
transaction. Failed readback uses the existing rollback path. An unchanged
launch performs no settings transaction writes.

`[SETTINGS-VERIFY]` in Debug logs shows each real path, CRC validity and flags;
expected `vsync=1 frame_skip=0 xinput=1`. A template name alone is not proof of
the settings actually installed.

## Evidence and limits

The supplied LW1 log is SHA-256
`4bd004eea981c5f88f855ebaf48c264574563bcd5e1aa62e31b065d8950a1fcf`,
ending at 469.196 seconds. The user places prematch/kickoff after roughly five
minutes, with unchanged clocks. "Frame skipping ON" was inferred from motion,
not seen in Settings.exe. A later clarification describes the old 2x-motion
symptom recurring; that symptom is retained as the test target.

- The run reports verified low-window mode with a 3130 MiB supplied heap and
  reaches a match. It has no logged terminal allocation/JIT failure. That does
  not rule out intermittent pressure or prove physical free RAM.
- Many late windows reach roughly 53–60 native presents/second. Presents do
  not count unique displayed frames, simulation updates or correct game speed.
- The file callback worker `sysFileCallbackThread` (tid 88) is near one full CPU
  core through much of the prolonged 80–250 second phase. The log does not
  identify its exact hot guest function or separate all loading/scene phases.
- Recorded directory metadata work totals about 1.4 seconds of server wall
  time by 60.7 seconds, and then stops increasing. That alone does not explain
  minutes of prematch delay.
- The current PC mirror's three settings files all have valid CRC and flags
  `0x0289`, with skipping off. This is not a readback of the Switch SD card.
  Therefore the migration bug is confirmed but its causality in this run is not.
- The optional Kitserver `gameplay.dll` attach fails with `c0000005` around
  13.9 seconds, although the game continues. The log does not prove that this
  plugin causes later jumps. This update does not alter third-party plugins.

Do not arbitrarily halve QPC, the game clock or the FPS cap to hide the symptom.
The Kitserver reference speeder changes QPF only for a non-default factor;
the local configuration uses factor 1. The LOD values around 100 are also
present in the reference game's default table, so their numeric size alone
is not evidence that the patch forces maximum detail. Reference sources:
[speeder.cpp](https://github.com/pes-modding/kitserver-tools-2010-2013/blob/master/kitserver13/src/speeder.cpp),
[lodmixer.h](https://github.com/pes-modding/kitserver-tools-2010-2013/blob/master/kitserver13/src/lodmixer.h).

## Debug measurements

Only Debug launch activates these maintenance-thread reports:

- Every five seconds, the existing read-only PES timing probe checks three
  code fingerprints, page permissions, object identity and pointer stability.
  `[FEX3-GAME]` reports live settings/object skip bits and raw scale bits.
  `[FEX3-GCLOCK]`/`[FEX3-PACER]` describe the game's frame timing state, not the
  scoreboard's simulation rate. Unknown images or unmapped data are skipped.
- Every ten seconds, existing frame/pipeline/shader/cache counters and SD read
  counters are reported. `[FEX3-PACE]` includes long intervals followed by
  short bursts; `[LW2-IO]` separates completed SD read wall time from counts.
  Summed wall times may overlap across threads and cannot be added into a
  single frame budget. Peak fields are explicitly cumulative since launch.

The on-disk patched executable does not match the old timing probe's three
fingerprints. The probe may only become applicable after startup has populated
the live image; **live support is not assumed**. If it reports unknown-image,
file readback and present/pipeline/SD counters still work; no guessed address
is dereferenced or written.

No new per-frame kernel query, thread suspension, profiler sampling, guest
write, speed multiplier, FPS cap or cache-size change is introduced. Reports
queue to the existing bounded RAM logger; only its existing writer touches the
Debug log. Ordinary Launch remains free of diagnostic SD writes. Functional
settings/save/history writes remain allowed.

## Verification

- ASan/UBSan: all four presets migrate a valid imported skipping-on profile,
  preserve unrelated bytes and bindings, produce three identical CRC-valid
  settings files, and avoid repeat writes. Existing 28 injected transaction
  failure/power-loss cases recover; corrupt data is rejected.
- ASan/UBSan: diagnostic cadence/normal-launch gating and SD counter deltas;
  read-only timing guard tests cover unsupported/unmapped data, stale objects,
  ring bounds and synthetic timing histories.
- Actual final ARM64 ELF under Unicorn: low-window admission/native allocation,
  Wine mapping recovery, diagnostic I/O gating, and LW2 normal/Debug report
  integration. Kernel, file services and heap are modeled; this is not a Switch
  match or a hardware performance test.
- Packaging verifies an NRO-only payload, exact LW1 binary rollback, source
  deltas and hash-bound evidence. The only native source changes relative to
  LW1 are runtime.c and rebased build paths; allocator/driver code is unchanged.

Reproduce with `tools/build-pes-low-window.py --revision 2 --work <fresh-dir>`,
`tests/pes_low_window_pacing_host.py`, `tests/pes_low_window_binary.py`, and
`tools/package-pes-low-window-pacing.py`. Evidence is included in the package.
