# FEX3 isolated self-suspend wake candidate

## Device evidence and boundary

Same-core device log SHA256:
`8d2245dc98784b20de81cf09685603a8f2cc7247cddfc0259a886b19b5767593`.
Video `SysDVR_2026_09_27_17_06_55.mp4`, SHA256
`690e869d60182dc19f850b687991d36432d88ee82f8dca9c17a82eb6a4b514cf`.
Archived together under `local/fex3/samecore-audit/<log hash>/`, including
`video-observations.md` with PTS-labelled clock readings.

Live scoreboard rate before opponent goal kick: 167 game seconds / 13 video
seconds. After goal kick: 122 / 15. After subsequent corner/replay/own goal-kick
sequence: 380 / 29. Dead-ball holds excluded. Recovery after this sequence does
not identify which event restored speed. First live kickoff clock crawls then
recovers; stationary pre-kickoff setup alone is not treated as a runtime freeze.

`EVENT elapsed_s` counts log-loop sleeps plus intervening work, not measured
wall time. Exact video/log offset remains unvalidated. Raw scale/ring fields
cannot measure live simulation speed. Same-core did not eliminate reported
symptoms; preserve that result, not a presumed improvement.

Log line 2016 reports 12669 resume requests in its long reporting window, with
mean RPC time 1002us; this includes waiting/descheduling, not isolated CPU cost.
Line 2019 reports 21426 completed self-suspends. Targeted select routing remains
disabled. Source shows self-suspend used the same condition as unrelated
select/start-gate event/semaphore notifications. This is avoidable wakeup work,
not proof it caused the observed goal-kick slowdown.

## Isolated change

Opt in with `--resume-gate` on FEX3. Default control remains unchanged.

- Park synchronous self-suspend on stack-owned condition keyed by object identity.
- Final matching resume (count 1 to 0) signals only that parked object.
- Invalid/noop/nested resumes do not broadcast; their status/count stay unchanged.
- Real final CREATE_SUSPENDED start-gate resume still uses shared broadcast.
- Thread termination explicitly wakes private waiters before reference release;
  existing broad termination notifications remain.
- Preserve predicate mutex, 20ms relative safety recheck, nested suspend counts,
  remote-running refusal and delayed reply until resumed.
- No object/thread ABI change, allocation, timer scaling or hot-path logging.
- Global select routing, affinity, shader path, DLLs and settings unchanged.
- Same-core policy retained solely to isolate one variable against latest run.

Changes in generated source restricted to `dlls/ntdll/unix/horizon.c` and
`wine-nx-probe/source/runtime.c`; PE source and payload hashes match baseline.
New marker: `[FEX3-RESUME] isolated self-suspend wake`.
Coarse cumulative metrics: waits/returns count condition entries/exits;
rechecks count returns still suspended; wakes count explicit signals, not kernel
scheduler wakeups; final/start/ignored describe resume handling.

## Verification

Host source-slice regression compiles actual generated handlers with real
pthread workers and modeled libnx/transport boundary. RED baseline returned
exit 42 with 40 irrelevant wakes. GREEN retained shared broadcasts for a real
start-gate sleeper but had zero irrelevant self-suspend wakes. 1000 concurrent
park/resume cycles passed under fatal AddressSanitizer/UndefinedBehaviorSanitizer.
Apple LeakSanitizer unavailable; leak detection disabled explicitly.

Twelve patch drift/reapplication cases rejected before writes. Three faulty
variants (missing termination signal, broad resume, wrong-object routing)
compiled and failed expected semantic checks. Final generated source hashes
matched build receipt and its source slices passed again without regeneration.

Integration: three tests passed, including exact native delta, unchanged PE,
repeatability and restoration. ARM64 cross-build exited 0.

Final ELF SHA256: `7cd6f0807cb6da03f54d086b62545ffc0dcea2e4c906688a4f363ddba3a0fcfb`.
Linked ARM64 emulator tests passed:

- 15 suspend/resume scenarios: private wait condition, 20ms recheck, status/count,
  object-selective signals, nested/noop/invalid and shared start gate.
- 5 unchanged yield/delay cases.
- 8 existing synchronization-routing scenarios.
- 16 pipeline observer bindings.
- Native restore register/NEON/FP status and fallback paths.
- Wine/FEX unwind plus shared module index, 576 tree operations.

Optimized Python is rejected by every required report-producing validator before
artifacts/report writes, including CLI and imported entrypoints. Six optimization
tests passed; the three legacy validator regressions include 54 subprocess cases.
Packaging tests exercise actual candidate artifacts, NRO-only boundary, refusal
to overwrite and corrupted/stale receipts. The packager independently runs
elf2nro on the tested ELF and compares complete NRO executable bytes, so separate
matching receipt hashes cannot hide an ELF/NRO mismatch. Packaging does not establish game
performance. Shipping archive is produced only after independent review.

## Build and device test

Build with GNU Bison 3.8+ on PATH:

    python3 -B tools/build-fex-runtime.py --integration --diagnostic --samecore-yield --resume-gate --build-root /Users/ibnuputra/.cache/pes13-nx-macos --toolchain /Users/ibnuputra/.cache/pes13-nx-macos/toolchains/llvm-mingw-20260505-ucrt-macos-universal --output-dir local/fex3/resume-gate --jobs 2

Packager: `python3 -B tools/package-fex3-resume-gate.py`.
Archive target: `dist/pes13-fex3-resume-gate.zip`.
Only SD replacement: `switch/pes13-fex/pes13-fex.nro`.

Close game completely and backup playable NRO plus log first. Keep DLLs,
settings.dat, dxvk.conf, saves, cache, preset and stock clocks fixed. Test first
kickoff, fast ball/shoot, opponent goal kick and corner sequence. Preserve log
and video before relaunch. Restore backed-up NRO if menus/kickoff regress.

Hardware validation remains pending. No claim that kickoff, rapid-action
stutter or event slow motion is fixed. Separately audited WOW64 floating-point
serialization/domain defects require DLL-level regressions and are not mixed
into this NRO-only candidate.
