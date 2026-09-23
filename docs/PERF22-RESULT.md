# PERF22: arithmetic improvement and persistent transition slowdown

The user reports smoother play, remaining stutter, a large slowdown after the
ball goes out/goal kick that persists until closing the application, and three
stalled loading attempts before a fourth successful run. The supplied log
contains that successful run through 260 seconds; it cannot explain the three
failed starts. The screenshot shows the loading spinner, without a fault code.

Archive: `local/perf23/perf22-result.log`, 104,354 bytes, SHA256
`271ab6a5cb2f279363817815357e888ccedfef158b8a07bd65edf92b3767d4ce`.
The build marker is `pes13-nx-0.2.0-perf22-floatmath`. Later selector reports
confirm X87DOUBLE=0, FASTROUND=1 and SAFEFLAGS=2. Sampling is off.

| Ten-second windows ending at | Present FPS range |
| --- | ---: |
| 40–50 s | 50.46–53.46 |
| 120–190 s | 16.18–16.98 |
| 210–260 s | 13.59–15.89 |

These are presents per elapsed second, not unique simulation frames or a
frame-time distribution. Scene labels are not recorded. The exact goal-kick
moment and any very short drop cannot be identified from these averages.
This is not a synchronized benchmark against PERF21.

The captured guest sequences match PERF21. X87DOUBLE=0 shrinks the large
`0x111ffa0` block from 3,712 to 3,112 native bytes and `0x113120c` from 320 to
264 bytes. Smaller code is evidence that the option reached the translator,
not proof of a particular throughput improvement or precision correctness.

## Concrete scheduler weakness

Around 190–200 seconds, busy worker 176 exits and worker 184 starts. Earlier,
176 reports approximately 91% on core 2. Afterwards, 184 reports about 29–41%
on core 3, where audio thread 52 also reports about 19–28%. Worker 124 remains
near 82% on core 1. The top-thread reports no longer show substantial core-2
work, and there is no balancing report after the worker replacement.

These reports name preferred cores, not full affinity masks, and cannot prove
worker 184's purpose or that it is movable. However, source inspection exposes
a related weakness: `wine_nx_thread_balance` admits a proposed redistribution
only when the busiest core improves by roughly five percentage points (unless
an unpinned busy thread is urgent). If worker 124 owns that maximum on its own,
separating two threads on a less-busy core cannot pass this admission test.

The host regression reproduces a layout approximating the late run: loads
500 on core0, 846 on core1, core2 empty, and 381+220+60 on core3, with main
thread affinity fixed. The old admission rejects redistributing the secondary
work; PERF23 can move one eligible thread to core2 without increasing the peak.
This demonstrates a policy weakness, not a measured hardware fix.

## Next step

PERF23 adds a bounded secondary balancing decision after the old decision is
rejected. It preserves PERF22's math emitters and presets byte-for-byte. No
arithmetic relaxation or forced affinity override is added.

Four previous logs are now retained so reopening a failed run does not erase
the evidence. If loading still fails, a separate math-control flag overlay
restores X87DOUBLE=1 while retaining FASTROUND=1 and the new diagnostics. That
can distinguish the latest arithmetic option from an older startup race.
The loading root cause remains unproven until a failed launch is captured.
