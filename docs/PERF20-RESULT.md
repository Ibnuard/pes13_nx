# PERF20 console result and next experiment

The supplied run is archived at `local/perf21/perf20-result.log`, 104,399
bytes, SHA-256 `8afbd6fdff515cad3347b3b359372432b3e5394d5e9b5afd5248aa2a73e2c0d5`.
`tools/analyze-perf20-result.py` generates the summary and capture counts.

| Approximate scene | Intervals ending at | Weighted presents/s |
| --- | --- | ---: |
| Team selection | 70–80 s | 18.08 |
| Late match | 130–190 s | 9.33 |

Late-match intervals range from 8.98 to 9.59 FPS. PERF20 did activate:
1,840 compiled blocks received 5,054 guard-pair eliminations across 2,681
runs. These are compilation counts, not execution frequency or time saved.
The exact PERF19 matrix patch also remains applied without rejection.
The thread sampler is off; PERF19's previous run used the sampler, so this
is not a controlled percentage-gain comparison. Scene labels are inferred.

At 190 seconds, worker 176 uses 92.8% of one core, main thread 4 74.1%, and
worker 124 66.5%, with all threads totaling 2.82 cores. Worker 124 used more
CPU in the prior log, but scene/clock differences prevent causal attribution.

The improved capture targeting returned all eight requested buckets:

- `0x93e4b0`: a complete 976-byte native block still has 16 FPCR reads and
  32 writes; the guest block has conditional control flow, so PERF20's
  conservative straight-line fusion does not cover it.
- `0x113120c`: a complete 1,000-byte native block has 19 FPCR reads and
  34 writes, including x87 multiplication/addition/conversion.
- `0x111ffa0`: a 1,466-byte guest block expands to 12,424 native bytes.
  The 8,192-byte partial capture alone has 171 FPCR reads and 340 writes.
  The guest code includes a loop. Do not treat the partial native listing
  as a complete-block proof or these static counts as measured CPU time.
- Other short captured blocks contain memory barriers and floating-point
  conversion overhead. The pass is not removing all sources of CPU cost.

The user permits Box64 argument experiments while retaining SAFEFLAGS.
PERF21 therefore tests FASTROUND=1 alone for newly compiled game .text
blocks after the first successful Vulkan present. It does not change
SAFEFLAGS, X87DOUBLE, FASTNAN, STRONGMEM, BIGBLOCK, CALLRET, WAIT or DIV0.

This run records `rld.dll` attached at `0xfa390000`, outside the selected
game .text range. Its own code remains on the baseline settings. The
earlier combined PERF4 failure did not isolate SAFEFLAGS as the cause of
the initialization failure; that remains an unproven hypothesis.
