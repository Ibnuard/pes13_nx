# Fixed-Compatible 2D slowdown

Log archived: local/perf11/perf11-compatible-2d.log (56666 bytes).
Build PERF11, DXVK 3.1.1, profiling off. enabled=0 active=0 BIGBLOCK=0
throughout: the requested fixed-Compatible control was successfully applied.

Intervals ending 30–90 seconds report 7.06, 8.50, 7.00, 3.98, 7.10,
6.05, 7.95 successful presents/s. The user identifies slow Konami splash and
PES intro; the log itself does not label scene boundaries.
At 100 seconds: 0.60 FPS; 110: zero; 120: 8.28; 130–150: 2.99–4.38.
Rendering resumes after the zero-frame interval, unlike a permanent stall.
One run passing loading does not establish the intermittent hang is fixed.

Guest threads 72 and 124 occupy near-full cores through the slow early
intervals. Host-present wall time is usually ~19–20 ms/call in that period,
but cannot be subtracted from asynchronous frame time to compute CPU cost.
Four compiler workers are configured; this is not proof all four are busy.
There are recurring earlier HMAP errors and substantial I/O counters.
Neither identifies the dominant loop without execution samples.

The fixed-profile translation_attempts counter is zero by design because
the per-block override path is disabled. It does not indicate interpreter
fallback, absent JIT compilation, or zero generated blocks.

Next evidence: use PERF11 sample-on for a short reproduction, then sample-off.
Symbolize with /home/blekjek/pes13-build/runtime-perf11-box64-044/wine-nx-runtime.elf.
Do not reuse PERF8 offsets after the Box64 upgrade. Sampling perturbs timing,
so use it to locate code, not claim FPS changes. Preserve NRO/DXVK/preset for
this run; avoid stacking more unmeasured presets or deleting shader caches.
