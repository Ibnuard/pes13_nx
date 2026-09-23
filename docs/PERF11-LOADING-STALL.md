# PERF11 first loading stall

Input archived as local/perf11/perf11-loading-stall.log (49,041 bytes).
The log identifies PERF11 Box64 0.4.4 and DXVK 3.1.1. It records 22/49/53/14
presents in intervals ending at 30/40/50/60 seconds, then zero at 70 and 80.
Threads 72 and 124 each occupy about 99% of a core in the final intervals;
both were created with guest entry 0x4da0e3. Server requests continue.
This is a live-process rendering stall, not a captured process exit.

The prior PERF10 hang eventually had one saturated core; this sample has two.
Do not equate equal guest start addresses with identical worker functions or
infer a particular spin loop without PC/call-stack evidence. Server select
wall times include concurrent waits and are not CPU consumption measurements.

HMAP reserve failures (errno 17) and backing-map failures (errno 22) precede
the stall. The reserve check rejects ranges that are already kernel/native
mapped. map_backing_at receives EINVAL as its failure argument, so errno 22
alone does not identify a specific invalid game allocation or kernel Result.
These are investigation candidates, not demonstrated causation.

A DXVK cache file was found, but no explicit cache-corruption or device-lost
error identifies it as the cause. A restart resets threads and address-space
layout as well as potentially changing disk cache state. Successful restart
therefore does not distinguish a timing race from cache or mapping behavior.
The user confirms HOME -> X -> Close between launches.

Next controlled test: disable the PERF8 post-present BIGBLOCK=1 override with
pes13-perf11-compatible-only.zip, keeping Box64 0.4.4 and installed DXVK fixed.
Expect enabled=0 active=0 BIGBLOCK=0. The policy translation_attempts counter
will remain zero when disabled; this does not mean JIT is inactive. Restore
with pes13-perf11-restore-post-present.zip. Keep successful and stalled logs
separate before the next launch overwrites them. No hardware result yet.
