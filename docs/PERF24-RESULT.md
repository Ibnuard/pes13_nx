# PERF24 hardware result and PERF25 target

The user reports smoother play, with remaining stutter during fast lofted balls
and FPS drops during replays. Clocks were unchanged from math-control:
CPU 1728 MHz, GPU 768 MHz, RAM 1600 MHz; resolution remains 1280 x 720.
This controls the clock difference but does not create a scene-matched benchmark.

Five supplied logs are archived in `local/perf25/results`. The current log is
238,873 bytes, SHA-256
`0adc2d237830c1334d937707b5958c89c0b78c0bc4f0145be4b75733f52ada47`.
It runs PERF24 through 300 seconds without a recorded exception or exit.
Previous-1 and previous-2 are failed PERF24 launches. Previous-3 and previous-4
are older PERF23 math-control runs; they must not be pooled as PERF24 samples.
`tools/analyze-perf24-result.py` records every input hash and the raw aggregates.

## Present cadence

Windows below are grouped by uptime, not synchronized scene labels. "3D" is
inferred from the user's sequence and the change in load, not detected by the tool.

| Report endpoints | Weighted presents/s | Quiet gaps >100 ms | Quiet gaps >200 ms |
| --- | ---: | ---: | ---: |
| 40-50 seconds | 54.06 | 5 / 867 | 3 / 867 |
| 120-170 seconds | 10.92 | 64 / 521 | 10 / 521 |
| 220-300 seconds | 12.46 | 17 / 894 | 0 / 894 |

The late section is steadier, but its average quiet gap is still about 80.0 ms.
30 presents/s would require about 33.3 ms. Present counts are not necessarily
unique simulation frames; the diagnostic does not establish game-speed correctness.
The supplied data cannot locate an exact lofted-ball or replay event.

Late host-present calls average 0.322 ms; none of the 1,123 calls exceeds 16.667 ms.
That is only CPU time spent in the host-present call. It does not measure all
GPU execution, driver work, rendering calls or preceding synchronization.
It is evidence against that particular call being the dominant stall, not proof
that the complete driver has no overhead.

Late worker samples are predominantly in translated x86: 188w about 89.2%,
124w about 74.1%, main thread 4w about 65.8%. Each has 897 samples.
These include blocked wall time and are not weighted by CPU cycles.
Thread CPU use is separately high. The evidence supports reducing guest-side
translation work; it does not justify moving arbitrary game logic to the GPU.

## Repeated startup crash

Both failed PERF24 launches read address `0x00000004` at guest PC `0x0115c36f`,
inside block `0x0115c356+0x2a`, with EAX and EDX zero. Both then record:

```
Unhandled page fault on read access to 00000004
[EXIT] NtTerminateProcess(self) exit_code=0xc0000005
```

The main thread subsequently sleeps in `NtTerminateProcess`; the loading image
can remain on screen. These two attempts are crashes, not demonstrated loading
deadlocks. Mapping warnings also occur in the successful run, so they alone
do not identify the cause. The executable is packed; disk bytes at this address
are not the runtime instructions. PERF25 therefore reserves a bounded capture
slot for the decrypted block containing this exact PC, even before first present.
No null-check bypass, forced success or claimed startup fix is included.

## Concrete optimization target

Worker 124w repeatedly samples the bucket containing `REP MOVSD` at `0x0093df43`.
The captured routine at `0x0093df30` sets ECX=238 and copies 952 bytes. The native
loop uses one 32-bit load and store per iteration. PERF25 adds a 64-bit pair
loop only for this exact fingerprinted routine, a post-present block environment,
forward direction, even count and eight-byte-aligned pointers. Other cases use
the original loop. Existing strong-memory barriers are retained.

The actual pinned encoders produce 483 executed instructions for the aligned
238-dword loop versus 955 before. This is an instruction count in an emulator,
not a Switch cycle measurement or a whole-game speedup prediction. How often
both pointers are aligned must be confirmed on hardware; a translation counter
does not measure runtime use of the fast branch.

The main PERF25 package disables CPU sampling while retaining coarse frame
metrics. A same-NRO control disables only pair-copy, so its result can be compared
without changing renderer, math policy or sampler state. The 30 FPS target
remains unproven, especially without overclocking.
