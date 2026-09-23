# PERF28 results — a sustained CPU worker limit

Five supplied runs all identify PERF28. Four stop on the same guest access
violation; one reaches matches. The user confirmed that the 2–3 minute portion
was match play. Other scene boundaries below are approximate inferences.

| Windows ending after launch | Successful presents/s | Observation |
| --- | ---: | --- |
| 40–50 s | 51.80 | Probable menu |
| 60–90 s | 26.90 | Probable selection/loading; substantial variability |
| 110–150 s | 18.91 | Early match; worker 176 near 97% of one core |
| 170–330 s | 15.34 | Later match; replacement worker 184 near 96% of one core |

Worker 184 has 1,695 samples in the later segment: 94.68% in translated x86,
93.56% attributed to the game EXE. Worker 124 remains busy as well; the existing
REP MOVSD copy routine is its largest reported individual instruction bucket
(8.66%). The main thread has substantially more native wait samples. This
supports targeting the translated game workers. It does not prove every driver
CPU cost is negligible or that extra GPU work could replace game simulation.

The later segment's quiet present intervals average 64.92 ms and the sampled
intervals 65.93 ms. Only two quiet intervals exceed 100 ms. This is largely a
sustained throughput limit, alongside transition stutters. Native host-present
calls average about 0.28 ms; that is not total rendering time or GPU time.
CPU sampling can perturb execution and includes blocked time. Present rate
does not establish correct simulation speed. There is no matched A/B run.

## Repeated startup failure

All four failed runs read address 4 at guest instruction `0x0115c36f` with
EAX=0, ESI=4 and the same requested key `0x0386`. The preceding lookup returns
no matching record and the caller dereferences it. The captured inferred table
has 38 readable records, no cap/read failures, no matching key and identical
8-byte-prefix hash `b0075c5c` in all four runs. No descending adjacent keys were
observed. The lookup capture itself begins with a jump into protected code;
it does not contain the lookup implementation.

This narrows the investigation to why that key/table state is reached. It does
not establish file corruption, a cache bug, or the root cause of the missing
record. Other threads can mutate the table during capture. No successful-run
snapshot of the same lookup is available. Skipping the failed dereference
would conceal the unresolved state and is not included.

## Next experiment

[PERF29](PERF29.md) enables conservative Box64 block growth in four measured
worker/CRT regions after first present. This aims to reduce exits between
small translated blocks while retaining established math and memory policies.
A same-NRO control disables this change. The existing copy optimization,
startup fault capture and native renderer remain in place.

Raw private evidence is archived in `local/perf29/results`, with SHA-256 in
`input-manifest.json`. `python tools/analyze-perf28-result.py` regenerates
`local/perf29/perf28-analysis.json`. `tools/decode-perf28.py` decodes the bounded
fault captures. The archived successful run has SHA-256
`3f299c868e775b9fa01d4cd2d11b7b50d06d571fa74d8976f79a270910e21daf`.
