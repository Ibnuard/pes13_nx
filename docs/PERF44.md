# PERF44: locate the free-kick transition stall

This full-NRO diagnostic build retains the PERF42 game policy and the exact
startup recovery used by the quiet PERF43 run. It adds bounded, CPU-side Vulkan
stage measurements without enabling the intrusive JIT sampler. It is **not**
an FPS optimization or a claim of 30 FPS on stock clocks.

The latest quiet PERF43 log (SHA-256
`b2dc7d8e0cc773d06fa6077dec90d305c42100719cb1e8ff041baedc346d3f44`)
reports 38.4 presents/s in the
interval ending at 150 s. A game worker exits before the 160 s report; another
starts before the 170 s report, when cadence falls to 19.3 presents/s. The
player places the free kick and pre-replay demo at 2.5–3 minutes and reports
that normal speed returns after a later goal kick. The supplied log ends at
190 s, before that recovery was captured. This brackets the scene
transition but does not prove the worker restart causes the drop. Host Present
itself rises only from about 1.2 to 1.6 ms; the rest of DXVK/NVK and game waits
were not measured by that counter.

Install `pes13-perf44-event-pipeline.zip` over the current SD installation and
launch the existing forwarder. It includes one `switch/pes13-nx/pes13-nx.nro`
with the existing icon and does not include game files, saves or `settings.dat`.
The `[BUILD]` marker must say `pes13-nx-0.2.0-perf44-event-pipeline`, and the
log must show `[INIT] profiler off` and `[PIPE44]` lines. Keep the same teams,
stadium, camera, resolution and clock settings. Reproduce the free kick, then
continue through the goal kick and at least 30 seconds of resumed play. Save
`pes13-nx.log` before launching again, because rotation can replace it.

`[PIPE44]` reports host wall time in Present, its lock/surface stages, acquire,
queue submit, fence/semaphore and idle calls. These spans may be nested or run
concurrently; do not sum them as a frame budget. They include descheduling and
do not measure GPU execution. The comparison with PERF43 quiet should use the
same scene and clocks; any timing instrumentation can affect cadence. Reapply
`pes13-perf42-startup-guard.zip` for the uninstrumented control.
