# FEX3 event/display audit

Status: display-control settings overlay prepared; slow-motion root cause remains
unproven. No Wine/FEX runtime semantics changed and no new NRO/DLL was built.

## Evidence identity

Repository base: `experimental/fex-core`,
`bdaf08cf9566623ce7d6507075a5f1ed22b9a601`, with uncommitted work preserved.

The log changed during the audit. Do not combine these runs:

- Earlier delegated audit: 270032 bytes, 2703 lines,
  SHA256 `b3cf3e1fba54e4c87d4e3fbe28349e57efe5226ede0adfe6dc76e8b349068550`.
- Rechecked current log: 316246 bytes, 3078 lines,
  SHA256 `5a2ae1ad42472221d190b7692851dad80a706d73e4b8a04856c414d8ff863c5c`.

The current run is archived unchanged under
`local/fex3/event-audit/5a2ae1ad42472221d190b7692851dad80a706d73e4b8a04856c414d8ff863c5c/`,
alongside speed, timing, sync, summary and raw game-state-line JSON. These local
artifacts are ignored by Git. References to log lines below refer to that hash.

## Applied: restore an unverified display field

`tools/make-settings.py` had relabeled word `0x18` as quality and changed it from
1 to 0 without establishing its meaning. The original committed writer called
it only a user-tested display profile. Returning width/height to 1280x720 did
not undo that separate change.

The pinned Kitserver source provides a concrete reason to avoid the quality
interpretation:

- `kitserver13/src/lodmixer_addr.h:19-32` places width, height and widescreen in
  three consecutive DWORDs.
- `lodmixer.cpp:116-119` places picture quality after the widescreen word.
- `lodmixer.cpp:423-447` selects widescreen 0 for 4:3 and 1 for 16:9.

Source: https://raw.githubusercontent.com/pes-modding/kitserver-tools-2010-2013/ca8d588105c493c5d8777e9e77341eb5ec3e65d5/kitserver13/src/lodmixer_addr.h

Source: https://raw.githubusercontent.com/pes-modding/kitserver-tools-2010-2013/ca8d588105c493c5d8777e9e77341eb5ec3e65d5/kitserver13/src/lodmixer.cpp

This address table supports PES2013 demo1, not the retail executable. It is
support for an aspect hypothesis, not proof of the retail disk layout. No
quality option was moved to another guessed offset.

Changes:

- Restore raw `0x18=1` in the generator and both repository presets.
- Remove the unverified `--quality` option and Low label.
- Preserve flags `0x0289`, Frame Skipping off, XInput, width/height 1280x720,
  words `0x1c=0`, `0x20=1`, and all controller bytes.
- Relative to the pre-rollback settings, only byte `0x18` and checksum bytes
  `0x0c-0x0d` changed. Relative to HEAD, only the skip flag and checksum differ.
- Validate the checksum independently with `binascii.crc_hqx`.

Actual format: 852 bytes, header `<III` = magic `0x46434557`, version 2, size
`0x354`. Checksum is `<H` at `0x0c`: complement of CRC16-CCITT, seed 0, over the
whole file with the checksum field zeroed. Flags are `<H` at `0x0e`.
Earlier claims of a 64-byte profile or checksum at offset zero were incorrect.

Current preset checksum: `0x3ebd`.
SHA256: `98e8d826f51f2c09f0db41746ab428d8d551e2e148e0432dc884336be4b01c31`.
The pre-rollback preset is backed up under `local/fex3/event-audit/` with its
SHA256 in the filename. This is a controlled rollback, not a verified visual
fix or measured quality/performance improvement.

## Current hardware log

- Startup still reports `pes13-fex3-timing-audit`, preset `fastest`, x87=64,
  TSO 0/0/0, targeted wake disabled.
- The first present at line 1024 is suboptimal, 1270x691. All 23 recorded
  observations after it have swapchain and client 1280x720, through present
  36000 at line 2984. Resolution is established; correct projection is not.
- All 131 timing samples have settings_skip=0 and object_skip=0. Their pacer
  rings have count=0 and zero frame-clock deltas; they cannot measure live
  simulation speed.
- Last six windows cover 60130 ms and 3532 presents: 58.739 host presents/s.
  This is not unique displayed FPS or simulation speed, and has no verified
  live-match/menu/OC attribution.
- After diagnostic elapsed 120000 ms, the 55 windows range from 48.861 to
  60.246 host presents/s. Gap bins contain 0-20 gaps above 50 ms through 100 ms
  per window, and 8 gaps above 100 ms in total. Histogram boundaries come from
  `src/runtime/fex_frame_metrics.h`, not rounded FPS estimates.
- The lowest window in that range is line 2249: 48.861 presents/s; native
  Present total averages 209 us at line 2251. Other work and scheduling remain
  outside that call; this does not measure GPU execution.
- A newly observed raw scale transition occurs at line 2268: `3f666666`
  (approximately 0.9) becomes `3f4ccccd` (approximately 0.8), after the report
  with elapsed_ms=391087. The new value persists through the final sample.
  No symptom marker associates this change with onset or recovery, and this
  object field is not a validated simulation-speed multiplier. Do not force it.
- Shared-clock average gaps are 1002-1022 us; launch-wide peak 7785 us.
  Last sampled self-suspend totals are 60728 entered/60728 returned, waiting=0.
  These samples do not rule out a transient wait elsewhere.
- No `[EXC]` record. Router counters are zero because targeted=0 bypasses that
  observer, not because all waits/notifications vanished.

## Source findings, not device causality

Wine pin: `1bc4e45163f0d2328cdfd35c7f471dd9821bb879`.
FEX pin: `e2f973fe931e6dc2ce523795e51ca1ac3ca85816`.
These are repository dependency pins, not a verified disassembly of the deployed
binary. The local generated build trees are unavailable.

### Wine affinity retry

`dlls/ntdll/unix/horizon.c:9135-9144`, `horizon_server_follow_client`, updates
`connection->core_mask` before `svcSetThreadCoreMask` and discards its result.
If the SVC fails once, another request with the same desired mask returns early
rather than retrying.

Source: https://raw.githubusercontent.com/danfromtico/wine-nx/1bc4e45163f0d2328cdfd35c7f471dd9821bb879/dlls/ntdll/unix/horizon.c

The parent audit independently compiled the exact function body with a mocked
SVC which fails once. Two requests produced:

- Original: expected-failing exit 1; requested=2, cached=2, actual=1, svc_calls=1.
- Scratch candidate caching only on success: exit 0; actual=2, svc_calls=2.

ASan/UBSan were enabled. This establishes a fault-injected source defect only.
No log evidence shows an SVC failure on the device; the candidate was not added
to runtime patches or the display overlay.

### FEX floating-point context

`Source/Windows/WOW64/Module.cpp:239-253,280-301` copies x87 data and FCW but
contains no explicit MXCSR transfer in load/store; reconstruction sets MxCsr to
`0x1f80` at line 337. WineUnixCall crosses flush/unlock/load at lines 443-446.
The raw x87 memcpy also warrants testing against internal representation and
TOP rotation for reduced-precision mode.

Source: https://raw.githubusercontent.com/FEX-Emu/FEX/e2f973fe931e6dc2ce523795e51ca1ac3ca85816/Source/Windows/WOW64/Module.cpp

The delegated source-slice audit reported failing tests for MXCSR transfer,
x87 TOP/F64 representation, and shared x87/SSE FPCR rounding/FTZ state. The
parent re-read the pinned bridge, but did not run a full FEX guest or reproduce
those FPU harnesses after their cleanup. These findings justify retained guest
regression tests and bounded telemetry, not a blanket FPCR reset or a claim
that PES slowdown has been explained. Native exception FPCR/FPSR roundtrip is a
separate path and already has coverage.

## Analyzer fixes and verification

`tools/analyze-fex-speed.py` retains histogram bins, source lines, actual
swapchain/client dimensions, and each thread report's original progress stamp.
Synthetic fixtures validate parsing, not match execution.

`tools/analyze-fex-sync-regression.py` now reports filtered_percent=null when
there are no candidates instead of dividing by zero. Its log parser imports
without ELF dependencies; pyelftools remains required for CLI ELF symbol work.
The current real control log now summarizes successfully. Historical
scenario-specific interpretation in this CLI was not reused for the new run.

Verified:

- `python -S -B -m unittest discover -s tests -p 'fex_*analysis.py' -v`:
  9 tests passed, including zero candidates, weighted nonzero totals, missing
  router records, inconsistent totals and dependency-free parser import.
- `python -S -B tests/settings_profile.py`: passed, both copies identical.
  The restored-display assertion failed before the binary correction.
- `python -B tests/fex_suspend_backoff.py`: 10000 rejected calls, zero injected
  delays, passed.
- Native `fex_frame_native`, `fex_pipeline_native`, `fex_delay_native` and
  `fex_game_timing_native`, compiled with `-std=c11 -O1 -g -Wall -Wextra -Werror
  -fsanitize=address,undefined -pthread`: all passed on host arm64.
- The exact affinity source fault-injection test above reproduced RED/GREEN.
- Real current log analyzed and archived by hash; no synthetic output used as
  device evidence.
- Settings overlay ZIP read back: all three payloads, manifest and README
  matched; ZIP integrity test passed.

Not verified:

- Full `unittest discover -s tests -p '*.py'` exits 1 with existing module-name
  collision: `perf14_mappings` imported from `tools` instead of `tests`.
  This is not an all-green full-suite result. Many other project tests require
  their documented generated source or binary inputs.
- `python3 -B tools/build-fex-module.py --horizon` exits 1:
  `Missing LLVM-MinGW toolchain: /Users/ibnuputra/.cache/pes13-nx/toolchains/llvm-mingw-20260505-ucrt-ubuntu-22.04-x86_64/bin`.
  The referenced WSL tree `/home/blekjek/pes13-build` is also absent locally.
- Generator end-to-end reconstruction needs the user's supported settings.exe,
  which is not available locally. Only CLI help and actual preset validation
  were exercised.
- No updated runtime build, device deployment, visual fix or slowdown recovery
  has been verified.

## Settings-only test artifact

`dist/pes13-fex3-display-control.zip`

SHA256: `0d1ed42e432f0cd59dfb8a038f8ce44fe402ae489a7d863a894a0902e2bd5718`.

Contains three identical settings.dat files at the known FEX candidate paths,
a manifest and Indonesian test/backup instructions. No NRO, DLL or dxvk.conf.
The established packager installs the `drive_c/KONAMI/...` copy
(`tools/package-fex3.py:150-154`); the current gameplay log does not identify its
actual settings read path.

Close PES and back up existing device settings before extracting. Keep all
other settings and clocks fixed. Check HUD/ball/player proportions with a
screenshot. Revert to the device backups if behavior regresses.

Further runtime work needs retained guest/source regression tests, a usable
build tree and synchronized normal/slow/recovered evidence. Candidate telemetry
is per-thread FCW/MXCSR/FPCR state at context boundaries, actual affinity/SVC
result, and pending suspend age. Keep probes bounded, opt-in and free of
hot-path SD logging. Do not alter clocks or force thread resumes to conceal the
symptom.
