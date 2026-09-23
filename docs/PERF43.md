# PERF43: sample the camera and post-replay CPU path

PERF43 is built from the PERF42 startup-guard package. It retains the same
DXVK, Mesa, Box64 version, game flags, math emitters, and guarded startup
recovery. Its only code change adds the already-used PERF37 JIT block/opcode
sampler. Both `configuration.ini` and PES13's `pes2013.wine-nx.txt` enable
`profile=1`; capture remains off. This is a diagnostic NRO, not a faster NRO.

Install `pes13-perf43-match-probe-r2.zip` at the SD root. Keep the existing
`drive_c` game and save files. Close the app via HOME > X before each run.
At CPU 1728, GPU 768 and RAM 1600 MHz, play a moving-camera match, then
through goal/replay/replay studio and at least 30 seconds after any slowdown.
Record approximate application uptime of the goal, replay and slowdown.
Save `switch/pes13-nx/pes13-nx.log` before another launch rotates it. Expected
markers are `[BUILD] pes13-nx-0.2.0-perf43-match-probe`,
`CPU sampler=2s/10s at 20ms`, `[JIT37-BLOCK]`, and `[PROF]`.

Sampling pauses selected threads and affects cadence. Do not use PERF43's
sampled present rate as a 30 FPS benchmark; compare the per-block samples
between the moving-camera and post-replay phases. `tools/analyze-perf43.py`
reads the log without additional Python dependencies. With the approximate
uptimes supplied by the tester, use `--before START:END --after START:END`
to compare the two phases. Restore `pes13-perf42-startup-guard.zip` after the
diagnostic run for quiet play.
