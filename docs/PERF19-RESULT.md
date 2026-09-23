# PERF19 console result

The supplied log is archived in `local/perf20/perf19-result.log`:
213,286 bytes, SHA-256
`e998d3e0f6d872b823366141fcbc506e5b09764b4933cffbdf050c769d67d17e`.
`tools/analyze-perf19-result.py` produces the numerical summary.

The matrix patch was actually applied: `identity=1 applied=1 rejected=0`.
The captured ARM64 block also matches the tested PERF19 patch byte-for-byte
(SHA-256 `810578ecc3cd0cb781f679ad8f3b231bdd61aabe12acb4629f7865d616773ada`).

| Approximate scene | Intervals ending at | Weighted presents/s |
| --- | --- | ---: |
| Team selection | 70–90 seconds | 11.92 |
| Late match | 160–230 seconds | 8.94 |

Late match interval rates range from 8.36 to 10.49 FPS. At 230 seconds,
thread 176 consumes 94.5% of a core, thread 124 87.7%, and the main thread
74.1%. Most samples of those threads are in translated guest code. The
worker at 124 repeatedly samples EXE offsets around `0x53b860`, `0x53df40`,
`0x537a00`, `0x53cfc0` and `0x53e4e0`. These are sampled address buckets,
not established function boundaries. Another worker is spread across a
larger set of game routines. The old matrix routine is no longer among
the listed dominant buckets in these late intervals.

This supports targeting game-code translation costs next. It does not
exclude driver/GPU costs, establish that any one worker is on the frame's
critical path, or prove a fixed FPS gain against PERF18. Scene boundaries
are inferred, clocks and scenes were not synchronized across runs, and
the 10 ms thread sampler is active. Samples include blocked time and only
four previously busy threads. Host present duration is not GPU duration.

The previous broad code-capture ranges sometimes selected a nearby short
block instead of the measured bucket. PERF20 selects the actual sampled
buckets and expands the same bounded capture mechanism to eight targets.
