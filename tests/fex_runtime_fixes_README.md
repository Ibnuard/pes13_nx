# Timer + affinity host regression

Scope: `tools/fex_runtime_fixes.py` applies only `dlls/ntdll/unix/horizon.c` through `apply(read, replace, project)`. Caller buffers and publishes source. Module performs one replacement only after all anchors validate; reapplication and drift fail without partial writes. No master patcher, PE, scheduler, self-suspend, guest-clock implementation or prepared-tree writes here.

## Run

```sh
# Offline retained verbatim source slices; all timer cases + affinity.
python3 tests/fex_runtime_fixes.py

# Exact full pin: patch in memory, never modify input.
python3 tests/fex_runtime_fixes.py --source /Users/ibnuputra/.cache/pes13-nx-macos/source

# Real generated source: test as-is; do not patch again.
python3 tests/fex_runtime_fixes.py --already-patched --source /Users/ibnuputra/.cache/pes13-nx-macos/fex-experiment/wine3/native-source

# Expected RED controls against original pin (each exits nonzero).
python3 tests/fex_runtime_fixes.py --unpatched --only timers --scenario normal
python3 tests/fex_runtime_fixes.py --unpatched --only affinity
```

Full audit takes exact pin plus an existing prepared native source **without** runtime fixes. It patches only memory and compiles source slices under host ASan/UBSan. Optional `--generated-source` checks final prepared source as-is too. It never rebuilds or writes Wine source.

```sh
python3 tests/fex_runtime_fixes_verify.py \
  --source /Users/ibnuputra/.cache/pes13-nx-macos/source \
  --native-source /Users/ibnuputra/.hermes/cache/scratch/fex-macos-audit-fw3zvdl2/native-source \
  --output /Users/ibnuputra/.hermes/cache/scratch/fex_runtime_fixes_report.json
```

Scratch native input shown above is local retained prepared source, not a permanent dependency. Supply another unpatched prepared native root when unavailable. `CC` selects compiler; `TMPDIR` controls disposable build location. Compiler failures never count as expected RED. Sanitizer errors are fatal, tests have timeouts, report preserves executed commands, hashes, stdout/stderr and return status.

## Provenance and coverage

- Base `autorunhq/autorun` `1bc4e45163f0d2328cdfd35c7f471dd9821bb879`; exact source and retained function ranges/hash checked against `fex_runtime_fixes_provenance.json`.
- Literal timer edits independently checked against retained diff from `51f94949d738c978bfb80a5118d7ffa4cf6b98ae`.
- Real timer handlers, select dispatcher, WAIT_ANY/WAIT_ALL/signal-and-wait, object wait, sleep and TIMER/EVENT signal/consume arms compiled from supplied source. Wire structs, transport, clocks, kernel waits and unrelated objects modeled.
- Real `fex_sync_horizon.h` router tested with targeted wake off/on. Native select source remains unchanged except timer updates and polling refresh. Self-suspend uses existing real pthread regression against in-memory generated handlers.
- Expected RED: pin signals on set; affinity caches before failed syscall; exact upstream cancel clears signal; stale polling after rearm/cancel; relative/periodic signed overflow; unbounded missed-period loop.
- Mutation controls remove select expiry update or armed-timer polling; regressions must fail.
- Fail-closed tests cover repeat apply, late anchor drift, duplicate anchor and absent source. Sibling `fex_sync_patches` order must produce identical `horizon.c`.
- Entire source outside timer helper/global and six intended functions remains byte-identical. All other static functions, including suspend/resume, are compared.

## Deliberate deviations from timer commit

1. Cancel stops future expiry but preserves current signaled state, per [Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-cancelwaitabletimer).
2. Relative deadlines beyond signed 64-bit range saturate before arithmetic; `INT64_MIN` never wraps into an already-due timer.
3. Periodic expiry skips missed periods in constant work while preserving phase. If next deadline is unrepresentable, retain current signal and disarm rather than overflow/repeat forever.
4. Select refreshes polling after wake: timers armed during wait get 1ms checks, canceled/consumed one-shots stop unnecessary 1ms checks. Existing deadline calculation, wait slice, condition wait and first-attempt signal rules remain intact.
5. Affinity cache advances only after `R_SUCCEEDED(svcSetThreadCoreMask(...))`; same requested mask retries after failure.

This remains a narrow backport, not complete Windows timer emulation. Existing wall-clock-based relative expiry and polling architecture are retained; no APC support added. Host tests do not prove Switch kernel behavior, shipping binary contents, PES timing improvement or hardware causality. Parent must regenerate prepared source after module changes and rerun `--already-patched` before claiming generated artifact validated.
