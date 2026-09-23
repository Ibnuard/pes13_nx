# PERF21 hardware result

The user reports a substantial improvement, working Box64 arguments, remaining
slow motion in matches and stutters around replay transitions. The run is
`pes13-nx-0.2.0-perf21-fastmath`, with continuous sampling and verbose logging off.
The archived log is 100,957 bytes, SHA256
`0fc5e14545238626dd98bb18b4a4b51c28f828b3ac51cb7ce06046aeb642bdcd`.

| Windows ending at uptime | Weighted presents/second | Range |
| --- | ---: | ---: |
| 40–50 s | 52.12 | 50.17–54.07 |
| 110–160 s | 17.00 | 16.28–18.24 |
| 170–240 s | 13.96 | 10.40–18.19 |

These are ten-second present-counter windows. The log does not label scenes,
so the early 2D / middle 3D / late mixed interpretation remains an inference
from the user's report, not a synchronized replay trace. It cannot identify
which individual window is a replay transition. Presents are not necessarily
unique simulation frames. The earlier PERF20 late-run average was 9.33, but
different scenes and timings prevent a controlled percentage comparison.

The final selector report confirms `game_FASTROUND=1`, `SAFEFLAGS=2`,
`X87DOUBLE=1`, `STRONGMEM=1`, and 103,538 completed selected translations.
These translation counters are not execution counts or CPU time. The exact
PERF19 matrix patch remains applied; PERF20 fusion remains enabled.

## Captured code supports the FASTROUND effect

Seven targets have the same complete guest byte sequences as the preceding
PERF20 captures. All seven current native captures are complete and have no
FPCR accesses. One target, slot 5, was not captured in this run.

| Guest start | PERF20 native bytes | PERF21 native bytes | Remaining FCVT instructions |
| --- | ---: | ---: | ---: |
| 0x93b85f | 152 | 112 | 2 |
| 0x93df30 | 144 | 144 | 0 |
| 0x9379f0 | 112 | 72 | 2 |
| 0x93cfb0 | 120 | 88 | 2 |
| 0x93e4b0 | 976 | 400 | 24 |
| 0x113120c | 1,000 | 320 | 17 |
| 0x111ffa0 | 12,424 | 3,712 | 256 |

The larger block now fits fully within the bounded snapshot. Its guest code
contains many x87 loads, arithmetic operations and stores, and the native code
still repeatedly widens single-precision values to double and narrows them
again. This is concrete motivation for trying Box64's `X87DOUBLE=0` policy.
Static counts do not establish the block's execution frequency or predicted FPS.

At 150 s the log records approximately 2.96 cores of aggregate thread CPU time,
including a worker at 88.3%, another at 80.8%, and the main thread at 62% of a
core. That is consistent with continuing CPU pressure. Host-present call times
alone are not GPU execution timings and cannot rule out GPU/driver work.

The next experiment retains the now hardware-tested FASTROUND policy and changes
only X87DOUBLE within that policy's scope. SAFEFLAGS remains 2. Reproduction:
`tools/decode-perf17.py` followed by `tools/analyze-perf21-result.py`; local
artifacts live under `local/perf22/` and are excluded from source distribution.
