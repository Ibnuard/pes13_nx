# PERF42 match result, camera/replay slowdown

Input: `C:/Users/Administrator/Documents/PES13LOGS/pes13-nx.log`, SHA-256
`9bec989a8267bca96f34d99ef551642f9c0f4d53e7dc97509e7c4edd4e809eea`.
Build marker: `pes13-nx-0.2.0-perf42-startup-guard`. This is one Switch run;
the CPU sampler was off. The player reports fast player movement but camera
stutter, followed by slow motion after goal, replay and replay studio.

The 120–210 second intervals average 19.00 presents/s. All 22 intervals ending
at 120–330 seconds average 20.17 presents/s. The final two intervals measure
15.72 and 18.69 presents/s. Earlier 30–56 presents/s intervals are not marked
as live match and cannot establish 30 FPS gameplay. The log has no exact scene
timestamp, so the replay transition cannot be assigned to one numeric row.
There is no recorded guest fault or exit, and no `[BOOT42]` guard activation.
One clean boot does not establish startup reliability.

The 120–210 second mean frame interval is about 52.6 ms. Reaching 30 FPS
requires at most 33.3 ms, a roughly 36.6% reduction in per-frame time in that
phase. During the busy intervals the game uses nearly three CPU-core
equivalents; the changing translated worker and another worker account for
much of it. The measured host `Present` call usually takes less than 2 ms,
but this excludes most DXVK, driver, and GPU work. Thus the log prioritizes
CPU/JIT attribution without proving that graphics work is free.

PERF43 retains the PERF42 game execution policy and adds bounded instruction
and guest-block samples. Its sampled FPS is **not** a production performance
comparison. A valid run should include a moving-camera match segment, a
goal/replay/replay-studio segment, and at least 30 seconds after slowdown;
the tester should record approximate application uptime for each transition.
Only then can the samples point to a specific CPU code path.
