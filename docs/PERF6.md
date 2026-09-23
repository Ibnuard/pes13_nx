# PERF6 fast jump-table experiment

**Known issue found during PERF8 work:** removing the translator-lock counter
alone left its `if` attached to the following real mutex lock. PERF8 removes
the entire diagnostic conditional and tests unconditional locking. Treat this
historical package as a diagnostic rollback, not a corrected baseline.

PERF5 is rejected: its final Box64 `-O2` build reached DXVK and showed four
frames, then produced no new Vulkan presents for 60 seconds while continuing
to execute about 40 million native dispatch entries and 1.6 million system
calls. That is a runtime/code-generation regression, not normal game load.

PERF6 returns every Box64 source file to PERF3's final `-O1` optimization and
keeps the seven Winlator Compatible values plus PERF3's ARM64 fast-suspend
`ntdll.dll` byte-for-byte. It changes only runtime overhead:

- `SAVE_MEM` is disabled. Box64 documents this option as a slower mode which
  adds a fifth jump-table level and one more memory read between translated
  blocks. PERF3 still reported more than 600 MB free after three minutes.
- Diagnostic atomic counters are removed from native block dispatch, RDTSC,
  Unix-call, syscall and Box64 run paths. These counters existed only for log
  analysis; PERF3 incremented the native-entry counter about 29 million times.

The thread balancer remains enabled so this test measures the Box64 changes.
Close PES through HOME, extract the overlay's complete `switch` directory to
the SD root and overwrite files. The game, settings, saves and controller data
are not included. Use the same forwarder.

Confirm the log contains `pes13-nx-0.2.0-perf6-fast-jumptable`, `[PERF6]`, and
all seven Compatible Box64 values. Test with the same safe CPU/RAM clocks and
the same teams, stadium and camera as PERF3. If boot or `rld.dll` regresses,
restore `pes13-perf4-rollback-to-perf3.zip`.

Build in WSL:
`PES_BUILD_ROOT=/home/blekjek/pes13-build python3 tools/build-perf6-test.py`.
