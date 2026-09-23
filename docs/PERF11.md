# PERF11 — Box64 v0.4.4, preserved PES preset

Box64 is pinned to 2f130fab1d6e1a4ee8a71dc60cfdfcc839ad192a, matching the
Autorun bootstrap inspected at 99de116c87e25f35ce345579ed18e86af494c2f8.
This updates the x86 execution core, not the entire Autorun runtime.

The isolated build uses runtime-perf11-source. The vendor checkout must be
clean at the pinned commit; Horizon adaptations are made to generated sources
and the local adapter. The older source/build directories are retained.

Adaptations include v0.4.4 fast block lookup, block entry/validation helpers,
environment macro signatures, CPUID interface and split executable/writable
mapping anchors. The compiler remains -O1, SAVE_MEM stays off, and the PERF10
ResumeThread wakeup fix is retained.

Preserved preset: SAFEFLAGS=2, FASTNAN=0, FASTROUND=0, X87DOUBLE=1,
STRONGMEM=1, CALLRET=0, BIGBLOCK=0 at boot. As in PERF8/PERF10,
BIGBLOCK becomes 1 per block after a successful Vulkan present. The package
checks the preset file byte-for-byte. Other Box64 defaults can differ between
versions; this is not a claim that all internal behavior is identical.

## Install

Close PES from HOME, then extract **pes13-perf11-box64.zip** to the SD root,
overwriting the switch folder. Use the existing forwarder. One NRO, same path.
Save, settings.dat and game binaries are unchanged. DXVK is not changed by
this overlay, allowing comparison with whichever PERF10 DXVK variant is installed.

Boot marker: pes13-nx-0.2.0-perf11-box64-044. Ten-second telemetry still uses
[PERF8]. Sampling/verbose remain off. Test boot first, then the same match
with the same clocks. Archive each log before starting the next run because
the current log may be overwritten. No performance or hang fix is confirmed
until tested on Switch.

**pes13-perf11-rollback.zip** restores the PERF10 NRO and runtime files without
changing DXVK. To compare the reported DXVK 3.1.1 hang against the original
renderer, use the separate pes13-perf10-rollback.zip (DXVK only).

## Latest hang evidence

local/perf11/perf10-hang.log identifies PERF10 and DXVK v3.1.1. At 150-201 s
there are zero new presents; translation attempts freeze at 19165 from 161 s.
Thread 128, created at guest address 0x4da0e3, keeps roughly one core busy.
Repeated get_handle_fd/event_op/resume_thread requests continue. This is a
live process with a stalled frame path, not evidence of a completed exit.
It does not identify the exact loop or prove which component causes it.

Earlier HMAP fixed-replacement failures deserve memory-manager investigation.
The log has no [EXIT] record, so it cannot explain the first-run exit report.
The user confirms HOME -> X -> Close between every attempt; do not attribute
this pattern merely to relaunching within the same still-running Wine process.
The unregistered COM class 304ce942-6e39-40d8-943a-b913c40c9cd4 belongs to
netfw.idl (firewall), not proof of a missing video decoder.
No cache deletion or speculative video-file removal is performed.
