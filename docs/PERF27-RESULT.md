# PERF27 hardware report, 22 September 2026

The successful run is meaningfully playable to the tester but remains below
the requested 30/60 FPS target. The user confirms that gameplay returns to its
earlier speed after replay/foul. Do not describe these transitions as a
persistent slowdown until application close.

Five uploaded logs were archived with hashes in `local/perf28/results/`.
Only the current log and previous-1/-2 are PERF27; previous-3 is PERF26 and
previous-4 is PERF25. `tools/analyze-perf27-result.py` creates the measured
summary in `local/perf28/perf27-analysis.json`.

| Inferred scene / report uptime | Presents/s | Present call, average wall ms |
| --- | ---: | ---: |
| Menu, 40–50 s | 53.30 | 0.640 |
| Selection, 60–110 s | 27.39 | 0.757 |
| Match, 120–170 s | 17.78 | 1.119 |
| Late match, 300–360 s | 15.58 | 0.384 |

Scene labels are inferred, without synchronized event timestamps. Successful
presents are not simulation frames. During the 180–210 s transition candidate,
individual windows range from 10.58 to 28.96 presents/s. This does not identify
the precise replay or foul. The screenshot's CPU is 1787.3 MHz, versus the
previously reported 1728; GPU 768 and RAM 1597.5 are approximately unchanged.
Scenes and clocks are not matched well enough for a percentage gain claim.

Targeted notifications filter 94.14% of candidate attempts during the initial
match segment and 93.38% in the late segment. Attempts filtered are not an
exact count of kernel wakeups prevented. No matching broadcast-control run
was supplied, so the impact on FPS cannot be isolated.

Late-match acquire/fence wall averages are approximately 0.105/0.046 ms;
present is 0.384 ms against roughly 64 ms between presents. These measured
calls alone cannot explain the gap. They also do not measure all driver CPU
work or GPU execution. CPU sampling was off: individual worker functions
cannot be identified from this run. Low GPU utilization alone does not prove
that driver overhead is absent.

## Startup failure

Both failed PERF27 runs contain access violation `c0000005`, read address 4,
at x86 `0115c36f`, followed by process termination. This is an actual crash,
not evidence that the loading animation is still progressing. It is the same
site captured in earlier experiments, predating targeted wakes and CALLRET=2.

Captured x86 and ARM64 show a lookup at `00438b40`, followed by checks that
can produce EAX=0, then `lea esi,[eax+4]; mov ebp,[esi]`. EBP holds `0386` at
the fault. A table stride of 164 and count from an object at offset 0x30 are
inferred from the caller. The lookup implementation and table contents are
not in these logs. The on-disk EXE is packed, so decoding the disk bytes at
that lookup address is not a reliable substitute for runtime bytes.

PERF28 captures this missing evidence after emulator unwind and enables
bounded CPU sampling. It preserves PERF27 translation/synchronization behavior
and does not replace the invalid read with fabricated success or skip work.
