# PERF4 balanced Box64 experiment

Hardware result: **failed** at `rld.dll` initialization. Do not use this
profile as a performance baseline. Restore PERF3 before testing PERF5. The
combined preset change in PERF4 does not identify which individual option
caused the failure.

PERF3 removed the suspend loop: Wine server requests fell from about 20 million
to 486 thousand and runtime syscalls from about 22 million to 1 million. At safe
clocks, full 3D remained CPU-bound. Two guest worker threads each occupied about
97 percent of a core while total usage reached 2.7 cores.

PERF4 retains the validated PERF3 ARM64 ntdll, DXVK shader cache,
`BOX64_DYNAREC_CALLRET=0`, and `BOX64_DYNAREC_X87DOUBLE=1`. It changes the
remaining conservative Winlator-compatible values to a balanced profile:

```
BOX64_DYNAREC_SAFEFLAGS=1
BOX64_DYNAREC_FASTNAN=1
BOX64_DYNAREC_FASTROUND=1
BOX64_DYNAREC_BIGBLOCK=1
BOX64_DYNAREC_STRONGMEM=0
```

These are standard Box64 performance modes, but this combination has not yet
been hardware validated for PES 2013. BIGBLOCK=1 is being retested only after
the independent suspend storm was removed.

Close PES through HOME. Extract the overlay's complete `switch` directory to
the SD root and overwrite the NRO, Box64 profile and ARM64 ntdll. Keep the game,
settings, saves, shader cache and controller profile. Use the same forwarder.

Test at the same safe clock and the same team, game plan, stadium and camera.
Run at least three minutes in a match, close through HOME, and return the log.
Confirm `pes13-nx-0.2.0-perf4-balanced`, the five settings above, and `[PERF4]`
appear in it. If boot, input, physics or rendering regresses, extract
`pes13-perf4-rollback-to-perf3.zip`.
