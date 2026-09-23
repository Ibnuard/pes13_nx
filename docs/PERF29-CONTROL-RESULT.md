# PERF29 control: event-associated stall reproduced, 2026-09-22

## Conclusion

Disabling worker block growth did not eliminate the user's repeating audio
and frame stalls after events such as fouls. Both new launches report
`worker_blocks=0 ready=0 selected=0 completed=0` and CPU sampling off.
This invalidates block growth as a necessary cause of the recurring stall;
it does not show whether growth can aggravate it. Keep it disabled until
there is evidence of benefit. No confirmed audio or runtime fix yet.

## Input identity

| Input | Build/mode | Evidence |
| --- | --- | --- |
| current | PERF29 control, sampling off | New 180-second run; stall reproduced |
| previous-1 | PERF29 control, sampling off | New startup access violation |
| previous-2 | PERF29 growth on, sampling off | Exact earlier bad run |
| previous-3 | PERF28, sampling on | Exact historical successful run |
| previous-4 | PERF28, sampling on | Exact historical startup failure |

Current SHA-256:
`3e0ca96ffae6bb646b7be3a40b94b363a0bf82e778e220f309ab58871f9a658f`.
New failed-launch SHA-256:
`2a318d696f8fb75077f7bfc4ec302054663b2af40a16b2ee506f30ee1389c2a2`.
Private raw copies and per-file hashes are preserved separately in
`local/perf29/control-20260922`, without replacing earlier evidence.

## Performance and transition

| Windows ending | Successful presents/s | Observation |
| --- | ---: | --- |
| 120-170 s | 15.53 weighted | Variable 11.39-21.16/s; not sustained 20 or 30 FPS |
| 160 s | 19.16 | Submit host mean 1.622 ms |
| 170 s | 16.58 | Submit host mean 1.139 ms |
| 180 s | 3.00 | Submit host mean 55.642 ms |

The final interval has 30 presents over 10.012 seconds. Seven quiet gaps
exceed 500 ms, six exceed one second. Its mean measured quiet gap is
317.164 ms; mean host present is only 0.663 ms. The launch-wide 3.422638-second
maximum gap already existed earlier: do not attribute it to the final event.

Submit host spans total 6.788380 seconds across 122 calls in the final interval.
Their launch-wide maximum rises from 343.000 to 970.451 ms. The long wall time
is inside host Vulkan submission, not the measured present lock or fence API:
present-lock total rounds to zero and fence-host mean is 0.285 ms. Submission
itself can wait on synchronization and resource availability. These spans
are not GPU execution timers, can overlap, and do not prove a GPU bottleneck.

Between reports 170 and 180, worker 188 exits, short-lived worker 196 starts
and exits, then worker 200 starts at the same guest entry `0x4da0e3`.
Main thread 4 drops from 65.4% to 13.2% of one core, while worker 124 remains
near 82.5%. Total reported occupancy drops from 2.92 to 1.95 cores. This is
not simply all cores reaching capacity. It associates worker turnover and
host-submit delay with the last stall, but does not prove either causes it.
Thread IDs are run-local and CPU sampling is absent in this run.

The log contains no synchronized foul/replay timestamp. Event context comes
from the user. It ends at the stalled interval: recovery after the event,
or a permanent stall until close, cannot be inferred. Present counts also
cannot detect repeated image contents or establish simulation speed.

## Audio and startup remain distinct

Only one PROGRESS audio observation is available: `audio_under=556` after
PERF8 uptime 120 s, before the final stall. There is no later audio counter
in this upload, so no audio-underrun delta can be calculated for that event.
The counter counts empty-queue pump observations, not unique echo episodes.
The audio pump source retains DMA ownership until release and does not
explicitly resubmit old queued frames. That does not rule out upstream
DirectSound/game buffer replay or timing faults; audio content is not logged.

The new previous-1 startup failure repeats guest EIP `0x0115c36f`, address 4,
EAX=0, key `0x0386`, 38 records, zero matches and hash `b0075c5c`. It also
occurs with block growth disabled. Do not hide it by skipping the dereference.

## Next diagnostic: same control, CPU sampling only

No evidence yet supports changing math, waits or audio-buffer size. A longer
audio buffer would not fix a near-one-second host-submit stall and can add
latency. The next artifact changes only the existing CPU sampler setting in
both configuration layers, keeping worker growth off and all runtime bytes
unchanged. This is diagnosis, not an FPS patch.

- `dist/pes13-perf29-control-sampling.zip`: three-file configuration overlay;
  worker growth=0, global profile=1, game profile=1.
- `dist/pes13-perf29-control-quiet.zip`: matching restore overlay;
  worker growth=0, global profile=0, game profile=0.

Both require the installed PERF29 NRO. Neither contains a replacement NRO,
game files, saves or settings.dat. The existing single-NRO forwarder stays.
Do **not** use the older `pes13-perf29-sampling.zip`: it enables growth too.

1. Close PES13-NX completely with HOME, X, Close. Extract the **control-sampling**
   ZIP to the SD root and overwrite its included configuration files.
2. Keep teams, stadium, camera, resolution, clocks and caches unchanged.
   Play until a foul/replay reproduces the sound/frame issue. Note rough
   elapsed real time, whether a replay is showing, and when it ends.
3. If practical, leave it running 30-60 seconds after symptoms begin. Note
   whether skipping the replay restores ordinary play. Stop sooner if needed.
4. Copy current and previous-1 through previous-4 logs before more launches.
5. Close completely and apply **control-quiet** for normal use afterward.

Expected initialized markers: PERF29 build, `worker_blocks=0 selected=0`,
`CPU sampler=2s/10s at 20ms`, `[SAMPLE24]` and `[PROF]` samples if sampling
permissions are available. Sampling can add stutter. The four targets are
chosen from the preceding CPU report; short-lived workers or event onset
may be missed. The extra post-event time improves the chance of capturing
the replacement worker and the thread blocked in host submit. Native PCs
can then be resolved against the exact existing PERF29 ELF; samples include
blocked wall time and must not be read as useful CPU time.

If repeated stalls have no useful native samples, the next source change
should add bounded stage/owner timing inside host submission and interval
audio-producer/pump metrics, not another speculative preset. No build was
needed or performed for these overlays.

## Reproduce

```
python tests/perf29_result.py
python tests/perf29_control_sampling.py
python tools/analyze-perf29-result.py local/perf29/control-20260922/results --prior local/perf29/regression-20260922/results --output local/perf29/control-20260922/analysis.json
python tools/package-perf29-control-sampling.py
```

Host tests validate mode isolation, hashes, profile switches, lifecycle log
ordering and sample parsing. They do not execute the Switch game or establish
audio correctness/performance. Earlier ZIPs and reports remain unchanged.
